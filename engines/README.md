# ReelReady engines

Small, single-purpose command-line tools the ReelReady orchestrator chains together. Each one reads files,
writes files, prints one summary line, and exits non-zero with a plain-English error. No API key is needed for
any of them. Full notes (timings, disk, backend switch, ffmpeg recipes): `docs/engines.md`.

Setup once: `uv venv .venv && uv pip install --python .venv/bin/python -r engines/requirements.txt`
(or `python3 -m venv .venv && .venv/bin/pip install -r engines/requirements.txt`). Needs `ffmpeg` on PATH;
captions also need Node (`npx`).

## The five contracts

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
    [--accent <word>] [--accent-color "#FFD60A"] [--max-words 3] [--keep-project <dir>]
# 2-3 word groups, each word pops in on its own timestamp; white heavy sans (bundled Inter) with a dark
# stroke; one accent word (given, else the longest content word). Pure fillers (um, uh) are left off the
# caption track; every other word is shown as spoken. Exit 1 with "disk is almost full" under 1 GB free.
```

Loudness (target -16 LUFS, QA window -20..-12): see "Loudness, stated once" in `docs/engines.md`.

Multi-clip: render each A-roll clip's EDL to `draft_01.mp4`, `draft_02.mp4`, ..., then
`python3 scripts/rr.py join-drafts draft.mp4 draft_01.mp4 draft_02.mp4` (stream copy + merged `draft.words.json`).

Smoke test: `bash tests/smoke/run.sh` (makes a 20 s talking-head stand-in with macOS `say`, runs all of the
above, asserts the retake and filler are gone and QA passes, then captions + QA; exits 1 on any failure, with
`CAPTIONS SKIPPED: <reason>` if the captions step fails).

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
7. Transition SFX and music: `.claude/skills/media-use/` in no-key mode (bundled SFX, user's `assets/music/`).
8. Render HyperFrames with `HYPERFRAMES_SKIP_SKILLS=1` so it never touches the bundled skills; mux the draft's
   audio back so loudness stays at -16 LUFS.
9. One signature effect per idea. Run `engines/qa.py` on every export and look at the frames before delivering.
10. HyperFrames refuses to render with under 1 GB free disk. `scripts/doctor.py` checks first (WARN under
    3 GB, FAIL under 1.5 GB); say so plainly and ask the user to free space.

`video-use/` is the vendored video-use editor (Browser Use, MIT): `helpers/pack_transcripts.py`,
`timeline_view.py`, `grade.py` and `render.py` for multi-take projects. Its `helpers/transcribe.py` falls back to
`engines/transcribe.py` when no ElevenLabs key is set.
