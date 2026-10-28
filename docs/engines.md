# ReelReady engines: reference

The engines live in `engines/`. They are plain Python 3.10+ scripts that shell out to ffmpeg (and, for
captions, to the HyperFrames CLI through `npx`). Every engine runs with zero API keys.

## Contracts

### 1. `engines/transcribe.py`

```bash
python3 engines/transcribe.py <clip> --out transcript.json \
  [--backend whisper-local|assemblyai|elevenlabs] [--model small] [--language en] [--env <file>]
```

Output:

```json
{"backend": "whisper-local", "language": "en", "model": "small",
 "words":    [{"w": "Hi,", "start": 0.0, "end": 0.6}],
 "segments": [{"text": "Hi, I'm, um, the owner of a small cafe.", "start": 0.0, "end": 3.28}]}
```

- Audio is decoded with ffmpeg to 16 kHz mono for every backend.
- `whisper-local` is primed with a short "um, uh, you know" prompt so Whisper writes fillers down instead of
  silently cleaning them. The cut engine needs to see them, and captions must be verbatim.
- Segments are re-split on sentence punctuation (and pauses over 0.8 s), so each segment is roughly one
  sentence. Retake detection works on these.

### 2. `engines/cut.py`

```bash
python3 engines/cut.py <clip> --transcript transcript.json --out edl.json \
  [--keep-hook-seconds 2] [--silence-db -35] [--min-gap 0.45] [--no-fillers] [--no-retakes]
```

Output: `source` (absolute path), `duration`, `hook_seconds`, `keep[]` (`reason: "speech"`), `removed[]`
(`reason: "dead-air" | "filler" | "retake"`, plus a human `detail`), and `stats` (seconds in/out, % removed,
count and seconds per reason, the settings used).

How it decides (logic adapted from the `yt-edit` skill's `deadair.py`):

| Reason | Rule |
| --- | --- |
| dead-air | ffmpeg `silencedetect` runs at `--silence-db` lasting `--min-gap` or longer. Trimmed from the middle, keeping 0.12 s of air on each side. Leading and trailing silence keep one breath. |
| filler | `um`, `uh`, `er`, `hmm` always. `like`, `so`, `you know`, `I mean` only when set off by a comma or a pause, so "I like coffee" survives. |
| retake | A sentence with a near-duplicate in the next two sentences (within 8 s): sequence ratio 0.8 or more, or 85% of the shorter one contained in the longer. The earlier take goes, the last take stays. |
| hook | Nothing is cut inside the first `--keep-hook-seconds`. A filler that straddles the boundary is kept whole. |

A removed filler or retake also swallows the pause after it, up to the next word. The pause before it stays
as the breath. Overlapping cuts are resolved into contiguous pieces, each with exactly one reason
(retake beats filler beats dead-air). Kept slivers under 0.2 s are dropped.

### 3. `engines/render_cut.py`

```bash
python3 engines/render_cut.py --edl edl.json --out draft.mp4 --aspect 9:16|16:9|4:5 [--fps 30] \
  [--crf 20] [--preset medium] [--transcript transcript.json]
```

- One seeked ffmpeg input per kept range, joined with 0.08 s `xfade` + `acrossfade` (the crossfade shrinks for
  very short ranges).
- Reframe: 9:16 to 1080x1920, 16:9 to 1920x1080, 4:5 to 1080x1350. A source already at the target aspect is only
  scaled. Anything else is scaled to cover and center-cropped (rotation metadata respected).
- Loudness: two-pass `loudnorm` (measure, then linear) to the kit target (see "Loudness, stated once").
- Output: H.264 High, yuv420p, CRF 20, AAC 192 kb/s at 48 kHz, `+faststart`.
- With `--transcript`, also writes `<out stem>.words.json` (`draft.words.json` for `draft.mp4`): each word re-timed onto the draft (a word belongs to the
  kept range it overlaps most, if that overlap is at least 0.1 s).

### 4. `engines/qa.py`

```bash
python3 engines/qa.py <mp4> --frames 6 --out <dir> [--expect 1080x1920] [--min-duration 3]
```

Writes `<dir>/probe.json` (duration, width, height, fps, has_audio, `audio.integrated_lufs`, `lra_lu`,
`true_peak_dbfs` from `ebur128`, the frame list, `pass`, `fails`) and `frame_01.jpg` ... `frame_06.jpg`
(512 px wide, evenly spaced at the centre of each sixth). Prints one line, `QA PASS: ...` or
`QA FAIL: <reasons> | ...`, and exits 0 or 1. It fails on: wrong resolution, duration under 3 s, no audio
stream, integrated loudness outside -20..-12 LUFS.

### 5. `engines/captions.py` (fast default for captions)

```bash
python3 engines/captions.py draft.mp4 --words draft.words.json --out captioned.mp4 \
  [--accent seven] [--accent-color "#FFD60A"] [--max-words 3] [--keep-project <dir>]
```

Builds a tiny HyperFrames project (the draft as a `<video>`, 2-3 word caption groups, each word popping in on its
own timestamp, Inter 700 and GSAP copied from the bundled `talking-head-recut` assets), renders it with the pinned
CLI (`npx hyperframes@0.8.143`, override with `REELREADY_HYPERFRAMES_VERSION`), then muxes the draft's audio back
bit-exact. Pure fillers are left off the caption track only. Telemetry and skill updates are switched off for
the render (`HYPERFRAMES_NO_TELEMETRY=1`, `HYPERFRAMES_SKIP_SKILLS=1`).

- Look: 2-3 word groups (`--max-words`, a new group after a 0.35 s pause), white heavy sans with a dark stroke,
  one accent word (`--accent`, else the longest content word) in `--accent-color` (reelready-edit passes
  `brand.colors.accent`). One look only: no brand fonts, boxes or karaoke fill.
- Used by reelready-edit when the caption card is C1 or the mix has no caption card. Other caption cards and
  words behind the subject go through the `embedded-captions` skill; captions inside an overlay layout through
  `talking-head-recut`.
- Exit 1 with a plain message on failure, including "disk is almost full" when HyperFrames has under 1 GB.

### Loudness, stated once

`render_cut.py` (and the music mix in reelready-edit) target -16 LUFS integrated, true peak -1.5 dBTP, LRA 11.
`captions.py` copies audio untouched. `qa.py` fails outside -20..-12 LUFS and reports `true_peak_dbfs`, which
must read <= -1.

### Multi-clip

Render each A-roll clip's EDL to its own draft (`draft_01.mp4`, ...; each gets `draft_01.words.json`), then
`python3 scripts/rr.py join-drafts draft.mp4 draft_01.mp4 draft_02.mp4`: ffmpeg concat demuxer with stream copy
(all drafts share render_cut's encode settings) plus one `draft.words.json` with every word shifted by the
running start time of its draft.

## The transcription backend switch

| Backend | Key | Where the audio goes | Notes |
| --- | --- | --- | --- |
| `whisper-local` (default) | none | nowhere: runs on this computer | faster-whisper, CPU, int8. `--model tiny/base/small/medium/large-v3` |
| `assemblyai` | `ASSEMBLYAI_API_KEY` | AssemblyAI (upload + poll) | `disfluencies: true` keeps fillers; sentences from `/sentences` |
| `elevenlabs` | `ELEVENLABS_API_KEY` | ElevenLabs Scribe | `scribe_v1`, word timestamps |

Keys are read from `--env <file>` when given (the orchestrator passes `<main folder>/.reelready/.env`),
otherwise from the process environment. Keys are never printed. A cloud backend with no key stops with:
`error: the 'assemblyai' backend needs ASSEMBLYAI_API_KEY, which is not set ... Use the free local backend
instead:  --backend whisper-local` (exit 2).

The same local engine backs the bundled skills: `watch` uses it for its Whisper fallback, and
`engines/video-use/helpers/transcribe.py` uses it when no ElevenLabs key is set.

## Where things are cached, and disk

| What | Where | Size |
| --- | --- | --- |
| Python venv (faster-whisper, requests, numpy, pillow, librosa, matplotlib) | `<repo>/.venv` | about 480 MB |
| Whisper `small` model (downloads on first use) | `~/.cache/huggingface/hub/` | about 480 MB (`tiny` 75 MB, `medium` 1.5 GB) |
| HyperFrames CLI (npx) | `~/.npm/_npx/` | about 130 MB |
| Headless Chrome, fonts, models for HyperFrames | `~/.cache/hyperframes/` | about 550 MB |
| Caption render temp project | system temp dir, removed on exit | a few MB plus frames |

HyperFrames refuses to render when the temp volume has under 1 GB free ("Low disk space"). `scripts/doctor.py`
checks the temp, repo and main-folder volumes first: WARN under 3 GB, FAIL (exit 1) under 1.5 GB.

## Speed on an M-series Mac (measured)

Measured on an Apple M1 (8-core CPU), CPU only, with a 60 s 1080x1920 test clip (42 s of `say` speech, 18 s of
silence) and the Whisper model already downloaded:

| Step | Time for the 60 s clip |
| --- | --- |
| `transcribe.py` (whisper-local, `small`, int8) | 26.9 s, model load included (about 0.45x real time) |
| `cut.py` | 0.5 s |
| `render_cut.py` (4 ranges, 38.6 s out, x264 `medium`) | 30.4 s |
| `qa.py` (38.6 s draft) | 0.9 s |

The 20 s smoke clip: transcribe 7.5 s, cut 0.3 s, render 3.4 s. Captions with HyperFrames on the 7.7 s draft:
22-29 s (Chrome start-up dominates; expect roughly 1-2 minutes for a 60 s draft). The first Whisper run also
downloads the model (about 480 MB). `--preset veryfast` roughly halves render time for previews.

## Smoke test

`bash tests/smoke/run.sh` makes a 20 s 1080x1920 clip (cream background, a drifting dark circle as the subject,
macOS `say -v Samantha` reading "Hi, I'm, um, the owner of a small cafe. We open at seven. Um. Come say hi, we
open at seven. Our address is on the screen."), then runs transcribe, cut, render_cut and qa, re-transcribes the
draft, and asserts: QA passes, the EDL has a retake for "We open at seven." and a filler cut after the hook, the
draft says "open at seven" exactly once, and at most one "um" remains (the one inside the protected 2 s hook).
It then burns captions with `captions.py` and runs QA on that too; if captions fail it prints
`CAPTIONS SKIPPED: <reason>` and exits 1. Outputs go to `tests/smoke/out/` (about 1 MB, git-ignored).

## ffmpeg recipe reference

Adapted from the `video-editing` skill in everything-claude-code (ECC), with ReelReady's own defaults.

```bash
# Extract a segment (stream copy, cuts on keyframes, fast but not frame-accurate)
ffmpeg -i raw.mp4 -ss 00:12:30 -to 00:15:45 -c copy segment_01.mp4

# Batch cut from a list (start,end,label)
while IFS=, read -r start end label; do
  ffmpeg -i raw.mp4 -ss "$start" -to "$end" -c copy "segments/${label}.mp4"
done < cuts.txt

# Concatenate same-codec segments losslessly
for f in segments/*.mp4; do echo "file '$f'"; done > concat.txt
ffmpeg -f concat -safe 0 -i concat.txt -c copy assembled.mp4

# 720p-wide proxy for fast previews (the spec's ingest step)
ffmpeg -i raw.mp4 -vf "scale=720:-2" -c:v libx264 -preset ultrafast -crf 28 -c:a aac proxy.mp4

# Audio for transcription (what every backend here uses)
ffmpeg -i raw.mp4 -vn -ac 1 -ar 16000 -c:a pcm_s16le audio.wav

# One-pass loudness normalisation (render_cut.py does the two-pass version)
ffmpeg -i in.mp4 -af loudnorm=I=-16:TP=-1.5:LRA=11 -c:v copy normalized.mp4

# Reframe 16:9 -> 9:16 (center crop) and 16:9 -> 1:1
ffmpeg -i in.mp4 -vf "crop=ih*9/16:ih,scale=1080:1920" vertical.mp4
ffmpeg -i in.mp4 -vf "crop=ih:ih,scale=1080:1080" square.mp4

# Scene changes (multi-shot check before captions)
ffmpeg -i in.mp4 -vf "select='gt(scene,0.3)',showinfo" -vsync vfr -f null - 2>&1 | grep showinfo

# Silence (cut.py uses -35 dB and 0.45 s)
ffmpeg -i in.mp4 -af silencedetect=noise=-35dB:d=0.45 -f null - 2>&1 | grep silence

# Measure loudness like qa.py
ffmpeg -i out.mp4 -vn -filter_complex ebur128=peak=true -f null - 2>&1 | tail -12

# 1 fps contact sheet (burned-in caption check, from embedded-captions)
ffmpeg -i in.mp4 -vf "fps=1,scale=160:-1,tile=10x5" sheet.png
```

Platform sizes: YouTube 16:9 1920x1080; TikTok / Reels / Shorts 9:16 1080x1920; Instagram feed 4:5 1080x1350
or 1:1 1080x1080. Keep captions out of the bottom ~25-30% of a 9:16 frame, where the app UI sits.

Note: this machine's Homebrew ffmpeg 8.1 has no `drawtext` / `subtitles` filters (no freetype or libass), so
ReelReady draws all text with HyperFrames, not ffmpeg.
