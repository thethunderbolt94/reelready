# ReelReady architecture

One page. Folders feed a five-step pipeline; Python engines do the deterministic work; Claude
drives the HyperFrames-based skills for everything visual; skills tie it together.

```
 USER'S MAIN FOLDER (~/Desktop/AI Video Editor)                 REPO (this kit)
 ┌──────────────────────────────┐                     ┌───────────────────────────────────┐
 │ raw footage/  (read only) ───┼──┐                  │ CLAUDE.md          operating brief│
 │ references/   (read only) ───┼─┐│                  │ reelready.config.json  brand+deflt│
 │ assets/       (read only) ───┼┐││                  │ scripts/ doctor setup init rr     │
 │ exports/      (WRITE)    ◄───┼┼┼┼─────────┐        │ engines/ transcribe cut render qa │
 │ .reelready/                  │││││        │        │ styles/cards/*.json + styleguide/ │
 │   style-profile.json ◄───────┼┼┼┼┼──┐     │        │ .claude/skills/...                │
 │   .env (keys, private)       │││││  │     │        └───────────────────────────────────┘
 │   work/<job>/ scratch ◄──────┼┼┼┼┼┐ │     │
 └──────────────────────────────┘│││││ │     │
                                 ▼▼▼▼▼ │     │
 PIPELINE (reelready-edit)             │     │
  1 INGEST   ffprobe, proxy, transcribe.py ─► work/transcript.json (word timings)
  2 CUT      cut.py ─► edl.json   render_cut.py ─► draft.mp4 + draft.words.json (re-timed)
             multi-clip: one EDL + draft_NN.mp4 per A-roll clip ─► rr.py join-drafts ─► draft.mp4
  3 PLAN     style mix (user IDs / pasted style-guide prompt / styles/mixes.json name
             > profile.default_mix > hook+captions+lower3rd+end card) ─► styles/cards/<ID>.json prompts
             ─► plan.md shown to user, wait for "go"         [GENERATED copy flagged]
  4 RENDER   card.engine ─► skill:
               captions  ─► engines/captions.py (fast default: plain verbatim word captions)
                          or embedded-captions   (designed looks, words behind subject via matting)
               overlay   ─► talking-head-recut  (lower-thirds, callouts, punch-ins)
               motion    ─► motion-graphics     (hook titles, end cards, transitions+SFX)
               composite ─► general-video       (b-roll cutaways, subject in front/behind)
               assets    ─► media-use           (only if assets/ lacks music/SFX)
             all on HyperFrames (npx hyperframes); music: rr.py duck-filter, -18 dB under speech
  5 QA       qa.py ─► probe.json + 6 frames, Claude looks ─► exports/<date>-<slug>/final.mp4
```

## Skills

Everything in `.claude/skills/` (21 folders + `ATTRIBUTION.md` with origins and licenses):

| Skill | Role | Triggers / called by |
|---|---|---|
| `reelready-setup` | doctor -> setup.sh -> init.py -> questionnaire -> profile -> study | first run, "install this", "set up reelready" |
| `reelready-study` | references -> `watch` (yt-dlp + frames + captions/local Whisper) -> `reference_style` | after setup, "study my references" |
| `reelready-edit` | the pipeline above | "edit this", "edit the newest clip", "use styles H1+C2", pasted style-guide prompt |
| `reelready-styles` | style guide page (`styleguide/serve.py`, port from config), mixes, hands off to reelready-edit | "show me the styles" |
| `embedded-captions` | designed word captions, behind-subject words | reelready-edit (captions cards other than the fast path) |
| `talking-head-recut` | lower-thirds, callouts, punch-ins over a talking head | reelready-edit (`overlay`, `cut` cards) |
| `motion-graphics` | hook titles, end cards, kinetic type, transitions | reelready-edit (`motion` cards) |
| `general-video` | b-roll cutaways, cut-outs, multi-layer builds | reelready-edit (`composite` cards) |
| `media-use` | music / SFX / images in no-key mode | reelready-edit, only when `assets/` has none |
| `hyperframes`, `hyperframes-core`, `-cli`, `-animation`, `-creative`, `-audio`, `-registry`, `-keyframes`, `-studio`, `hyperframes-helper` | the HyperFrames framework the visual skills build on | the engine skills above |
| `watch` | download + frames + transcript for any video | reelready-study |
| `yt-edit` | dead-air / filler / retake logic (`deadair.py`) | source of `engines/cut.py`'s rules |

## Contracts

All engines: `python3 scripts/rr.py run -- python3 engines/<x>.py ...` from the repo root. Full flags and
output schemas: `engines/README.md` and `docs/engines.md`.

| Command | In | Out |
|---|---|---|
| `engines/transcribe.py <clip> --out t.json [--backend whisper-local\|assemblyai\|elevenlabs] [--model small] [--language en] [--env f]` | clip | `{backend, language, words:[{w,start,end}], segments:[{text,start,end}]}` |
| `engines/cut.py <clip> --transcript t.json --out edl.json [--keep-hook-seconds 2] [--silence-db -35] [--min-gap 0.45] [--no-fillers] [--no-retakes]` | clip + words | `{source, duration, hook_seconds, keep[], removed[], stats}` |
| `engines/render_cut.py --edl edl.json --out draft.mp4 [--aspect 9:16\|16:9\|4:5] [--fps 30] [--crf 20] [--preset medium] [--transcript t.json]` | EDL | `draft.mp4` (-16 LUFS) + `draft.words.json` (only with `--transcript`; named `<out stem>.words.json`) |
| `engines/captions.py <video> --words draft.words.json --out captioned.mp4 [--accent word] [--accent-color #hex] [--max-words 3] [--keep-project dir]` | video + words on its timeline | captioned MP4, input audio copied bit-exact |
| `engines/qa.py <mp4> --frames 6 --out dir [--expect WxH] [--min-duration 3]` | export | `probe.json`, `frame_01..06.jpg`, `QA PASS/FAIL` line, exit 0/1 |
| `scripts/rr.py join-drafts <out.mp4> <draft_01.mp4> ...` | render_cut drafts | joined MP4 + merged `<out stem>.words.json` |
| `scripts/rr.py duck-filter <words.json> [--duration S]` | words | ffmpeg volume filter: music -18 dB under speech |
| `scripts/rr.py run -- <cmd>` | any engine | runs with repo `.venv` + `<main>/.reelready/.env` |
| `scripts/doctor.py [--fast] [--json]` | - | dependency + free-disk table; exit 1 on MISS or FAIL (under 1.5 GB free) |

Loudness target and QA window: "Loudness, stated once" in `docs/engines.md`.

## Invariants

- Agent writes only to `exports/` and `<main>/.reelready/` (profile: `<main>/.reelready/style-profile.json`).
  User media is never modified.
- Zero keys required. Keys live only in `<main>/.reelready/.env`, never in the repo or chat.
- Captions verbatim; generated copy flagged for approval; one signature effect per idea.
- No "done" without `qa.py` and a look at the frames.
- Brand strings come from `reelready.config.json`.
