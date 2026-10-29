# ReelReady engines

Small, single-purpose command-line tools the ReelReady orchestrator chains together. Each one reads files,
writes files, prints one summary line, and exits non-zero with a plain-English error. No API key is needed for
any of them. Full notes (timings, disk, backend switch, ffmpeg recipes): `docs/engines.md`.

Setup once: `uv venv .venv && uv pip install --python .venv/bin/python -r engines/requirements.txt`
(or `python3 -m venv .venv && .venv/bin/pip install -r engines/requirements.txt`). Needs `ffmpeg` on PATH;
captions also need Node (`npx`).

## The eight contracts

```bash
# 1. Transcribe -> word timestamps
python3 engines/transcribe.py <clip> --out transcript.json \
    [--backend whisper-local|assemblyai|elevenlabs] [--model small] [--language en] [--env <main>/.reelready/.env]
# -> {"backend","language","words":[{"w","start","end"}],"segments":[{"text","start","end"}]}

# 2. Cut -> edit decision list (dead air, fillers, retakes; first 2 s hook never cut)
python3 engines/cut.py <clip> --transcript transcript.json --out edl.json \
    [--keep-hook-seconds 2] [--silence-db -35] [--min-gap 0.45]
# -> {"source","duration","hook_seconds","keep":[{"start","end","reason":"speech"}],
#     "removed":[{"start","end","reason":"dead-air|filler|retake","detail"}],"stats":{...}}

# 3. Render the cut -> draft.mp4 (0.08 s crossfades, reframe, -16 LUFS, H.264 High, AAC 192k, faststart)
python3 engines/render_cut.py --edl edl.json --out draft.mp4 [--aspect 9:16|16:9|4:5] [--fps 30] \
    [--crf 20] [--preset medium|veryfast] [--transcript transcript.json]
# --transcript also writes <out stem>.words.json (draft.words.json): words re-timed onto the draft

# 4. QA -> probe.json + frame_01..06.jpg + one "QA PASS ..." / "QA FAIL ..." line (exit 0 / 1)
python3 engines/qa.py <mp4> --frames 6 --out <dir> [--expect 1080x1920] [--min-duration 3]

# 5. Captions (fast default) -> verbatim word-timed burn-in with HyperFrames, input audio copied bit-exact
python3 engines/captions.py <video> --words draft.words.json --out captioned.mp4 \
    [--accent <word>] [--accent-color "#FFD60A"] [--max-words 3] [--keep-project <dir>] \
    [--font <brand.ttf|otf|woff|woff2>] [--font-family "<CSS name>"] [--font-weight 800]
# 2-3 word groups, each word pops in on its own timestamp; white heavy sans (bundled Inter) with a dark
# stroke; one accent word (given, else the longest content word). Pure fillers (um, uh) are left off the
# caption track; every other word is shown as spoken. Exit 1 with "disk is almost full" under 1 GB free.
# --font (absolute, or relative to the main folder / its assets/) puts the brand font first, Inter as the
# fallback; --font-family defaults to the file stem; weight stays 800 (regular files get synthesized bold)
# unless --font-weight pins it. Missing/unsupported file (.ttc too): one "warning: font not found" line, Inter.
# Also writes <out stem>.captions.json: {font_family, font_source: brand|bundled-inter|system-fallback,
# font_path, accent_color, accent_word, max_words, groups, words} (the taste gate reads it).

# 6. Sound -> voice polish + SFX + room-tone bed (+ ducked music), -16 LUFS / -1.5 dBTP, video stream-copied
python3 engines/sound.py <video> --out sound.mp4 [--edl edl.json] [--captions draft.words.json] \
    [--preset clean|punchy|cinematic|calm] [--hook-seconds 2] [--music track.mp3] [--no-bed]
# Voice: highpass 80 Hz, deesser, 3:1 compressor at -18 dB, then two-pass loudnorm on the whole mix.
# Cuts come from the EDL (render_cut's timeline, crossfades included), else scene detection (scene > 0.4).
# clean/calm: short whoosh per cut (clean adds one click at the first caption); punchy: whoosh per cut,
# riser cresting at the end of the hook + impact hit, pop per caption group, sparkle on words marked
# "emphasis"; cinematic: cinematic whoosh, riser + hit, longer tails with a light echo. SFX sit -14 dB
# (cuts, hit) / -20 dB (pops, riser) under the voice. Bed: pink noise, lowpass 400 Hz, ~-45 LUFS.
# --music: looped/trimmed, sidechain-ducked to ~-22 dB under speech, 0.5 s in / 1.5 s out.
# Also writes <out stem>.sound.json (cut times + every placed sound). SFX files: engines/sfx/ (ATTRIBUTION.md).

# 7. Story -> edl.story.json: the EDL's keep list split at sentence boundaries and reordered/dropped
python3 engines/story.py --edl edl.json --transcript transcript.json --list            # numbered sentences
python3 engines/story.py --edl edl.json --transcript transcript.json --order 3,0,1,2 --drop 4 --out edl.story.json
# Words and audio untouched: it can only choose WHICH sentences play and in WHAT order (render_cut plays
# keep in list order). Fillers/retakes cut earlier stay cut. Adds "story":{order,sentences} to the EDL.

# 8. Taste gate -> one "TASTE ok|FAIL|note <rule>: <reason>" line per rule, then "TASTE PASS (n rules)" or
#    "TASTE FAIL: generic edit, <k> rule(s): a, b" (exit 0 / 1). Stdlib only; runs after qa.py, before "done".
python3 engines/taste.py --profile <main>/.reelready/style-profile.json --plan <export_dir>/plan.md \
    [--captions captioned.captions.json] [--sound sound.sound.json] [--mix H1,C1,L2,O1,S2] [--strict]
# Rules: brand-choices (plan.md "## Brand choices" has >= 3 bullets, each naming a brand hex, brand font,
# "logo" or a 3-word reference_style phrase), palette-in-plan (>= 2 brand colors named there), accent-color
# (captions accent = brand.colors.accent, never the #FFD60A default), brand-font (brand files on file ->
# font_source "brand"), signature (exactly one house_style.signature card in the mix), sound-preset (S card
# -> preset: S1 clean, S2 punchy, S3 cinematic, S4 calm, S5 clean + music). No --mix -> profile.default_mix.
# "note" = could not check (optional file missing, or profile has nothing to compare); --strict makes notes FAIL.
```

Loudness (target -16 LUFS, QA window -20..-12): see "Loudness, stated once" in `docs/engines.md`.

Multi-clip: render each A-roll clip's EDL to `draft_01.mp4`, `draft_02.mp4`, ..., then
`python3 scripts/rr.py join-drafts draft.mp4 draft_01.mp4 draft_02.mp4` (stream copy + merged `draft.words.json`).

Smoke test: `bash tests/smoke/run.sh` (makes a 20 s talking-head stand-in with macOS `say`, runs all of the
above, asserts the retake and filler are gone and QA passes, then sound (punchy) + QA, then captions + QA, then brand-font captions + QA, then the taste gate on
`tests/smoke/fixtures/` (on-brand must PASS, generic must FAIL); exits 1 on any failure, with
`CAPTIONS SKIPPED: <reason>` if the captions step fails, `TASTE GATE DID NOT CATCH GENERIC` if the gate passes a generic edit).

## How Claude drives captions and overlays

1. Engines do the deterministic part: transcribe -> cut -> render_cut -> qa. Never caption before the cut.
2. Captions are verbatim. Use `draft.words.json` (or re-run `transcribe.py` on the draft); never rewrite words.
3. Captions: `engines/captions.py` is the fast default (caption card C1, or no caption card). Other caption
   cards, brand-font captions, behind-the-subject hero words (matting): follow
   `.claude/skills/embedded-captions/SKILL.md`. Captions inside an overlay layout: `talking-head-recut`.
4. Lower-thirds, stat cards, end cards, kinetic type: `.claude/skills/motion-graphics/` (categories/lower-thirds etc.).
5. Talking-head with cards beside/over the speaker: `.claude/skills/talking-head-recut/`.
6. Anything else HTML-to-video: route through `.claude/skills/hyperframes/` -> `hyperframes-core` (composition
   rules), `hyperframes-animation` (motion, transitions), `hyperframes-creative` (palettes, type).
7. Sound pass (SFX on cuts, hook, captions; bed; ducked music): `engines/sound.py` after captions, before QA,
   preset from the mix's S card. `.claude/skills/media-use/` stays the fallback for other SFX or music.
8. Render HyperFrames with `HYPERFRAMES_SKIP_SKILLS=1` so it never touches the bundled skills; mux the draft's
   audio back so loudness stays at -16 LUFS.
9. One signature effect per idea. Run `engines/qa.py` on every export and look at the frames before delivering.
10. HyperFrames refuses to render with under 1 GB free disk. `scripts/doctor.py` checks first (WARN under
    3 GB, FAIL under 1.5 GB); say so plainly and ask the user to free space.

`video-use/` is the vendored video-use editor (Browser Use, MIT): `helpers/pack_transcripts.py`,
`timeline_view.py`, `grade.py` and `render.py` for multi-take projects. Its `helpers/transcribe.py` falls back to
`engines/transcribe.py` when no ElevenLabs key is set.
