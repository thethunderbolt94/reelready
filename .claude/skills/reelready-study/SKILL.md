---
name: reelready-study
description: ReelReady reference study. Watches the user's reference videos (Instagram, TikTok, YouTube links from the style profile, or files in references/) with the bundled watch skill, free (yt-dlp + frames + native captions or local Whisper, no keys), and writes profile.reference_style plus a 10-line human summary. Use after setup, or when the user says "study my references", "learn from these videos", or adds new reference links.
---

# ReelReady study

Goal: learn the FEEL of videos the user admires (captions, pacing, color, hooks, music, effects)
so edits match it. Borrow patterns, never content. Free: no paid transcription subscription.

## 1. Gather sources

```bash
python3 scripts/rr.py where --json      # -> main_folder, profile, references, work
```
Sources = `profile.references[].url` + new links the user just gave + video files in references/
(ignore README.txt and links.txt; read links.txt for extra URLs, skip `#` lines). A relative path
like `references/x.mp4` is relative to the main folder: pass `<main_folder>/references/x.mp4`.
New links -> add them to `profile.references` (send the whole list: lists are replaced on merge).
Cap at 5; if more, ask which 5 matter most. Work dir: `<work>/study/<n>/`.

## 2. Watch each one

The bundled `watch` skill downloads (yt-dlp), pulls frames and gets a transcript: native captions
first, then free local Whisper (no key, nothing uploaded). Run it through `rr.py run` so the repo's
yt-dlp and ffmpeg are on PATH:
```bash
python3 scripts/rr.py run -- python3 .claude/skills/watch/scripts/watch.py "<url-or-file>" --out-dir "<work>/study/<n>" --max-frames 12
```
Don't pass `--whisper assemblyai|groq|openai` (those upload the audio) unless the user asks.
- Read every frame it lists, in one parallel batch.
- The video: a link downloads to `<work>/study/<n>/download/video.<ext>` (usually .mp4; `ls` it); a local
  file is used in place, at its original path in references/ (read-only: never move or delete it).
- watch's transcript is sentence-level. For real pacing numbers (words/sec, gaps), get word timings
  from the local engine (skip if the video has no speech):
  `python3 scripts/rr.py run -- python3 engines/transcribe.py "<video>" --out "<work>/study/<n>/transcript.json"`
- Cuts: `ffmpeg -i "<video>" -vf "select='gt(scene,0.3)',showinfo" -f null - 2>&1 | grep -c pts_time`;
  duration: `ffprobe -v error -show_entries format=duration -of csv=p=0 "<video>"`
  -> average shot length = duration / (cuts + 1).

**Failures are normal. Be polite and move on, never retry in a loop:**
- login wall, private account, "rate-limit", "unavailable", HTTP 403/404, region lock -> skip it.
  Record `{url, reason}` in `reference_style.skipped`. Tell the user once, kindly: "I couldn't open
  2 of your links (Instagram asks for a login on those). If you save them to your phone and drop the
  videos in the references folder, I can study them from there."
- No internet ("could not resolve host", "timed out", "network is unreachable") on the first link ->
  stop trying links. Study only local files, and say once: "I can't reach the internet right now, so
  I'll study your links later. Say 'study my references' when you're back online."
- yt-dlp missing -> `bash scripts/setup.sh` with the user's OK, then continue.
- Never ask for, use, or store the user's social-media passwords or cookies.

## 3. Write the style

Look across all studied videos for what they share. Write `<work>/study/reference_style.json`, then
merge it into the profile:
```bash
python3 scripts/rr.py profile-merge "<work>/study/reference_style.json"
```
with `{"reference_style": {...}}` containing exactly:
- `caption_style`: size, weight, case, color, box/shadow, words per chunk, position, animation
- `pacing`: average shot length (s), speech rate, longest pause allowed, when the hook lands
- `color_notes`: warmth, contrast, saturation, any consistent grade; mention the brand palette fit
- `hook_patterns`: list, e.g. "question to camera", "result first", "text-only first frame"
- `music_use`: genre/energy, how loud under speech, swells, silence moments
- `effects_seen`: list of concrete effects (punch-in zoom, title behind subject, whip transition)
- `do_not_copy`: things that belong to that creator (catchphrases, logos, characters, exact songs,
  signature intros). We match the feel, not the identity.
- `summary`: the 10-line human summary (below), as one string with newlines
- `studied_at`: ISO time; `sources`: urls/files studied; `skipped`: [{url, reason}]

Map what you saw to style card IDs when obvious (read `styles/cards/*.json`) and list them in line 9.
Called from **reelready-setup**: never write `default_mix` (setup's house style step does that).
Otherwise: write `default_mix` only if the user says yes.

## 4. Tell the user (10 lines, plain words)

```
What your favourite videos have in common:
1. Captions: ...
2. Pace: about one cut every N seconds ...
3. Hook: ...
4. Color: ...
5. Music: ...
6. Effects: ...
7. What we'll borrow for you: ...
8. What we won't copy: ...
9. Styles that match: <IDs + names>
10. Skipped: <n links + why, or "none">
```
Outside setup, line 9 may add: (say "show me the styles" to see them).
Afterwards delete only the downloads: `rm -f "<work>"/study/*/download/video.{mp4,webm,mkv,mov}` (keep transcripts and
the JSON). Never delete anything in references/.
