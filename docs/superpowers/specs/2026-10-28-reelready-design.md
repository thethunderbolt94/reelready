# ReelReady — design spec (2026-10-28)

Working brand: **ReelReady by Suhaas Builds**. Rename lives in one place: `reelready.config.json` → `brand.name`, `brand.by`, `brand.url`.

## Intent
A free, installable AI video editor kit for Claude Code. A non-technical small-business owner
drops phone clips in a folder and gets back a cut, captioned, motion-graphic'd 9:16 video ready
to post. The kit is the marketing ("give away the secret"); setup, style tuning and a Telegram
concierge are the paid implementation sold by Thrive Labs.

First client: a local cafe owner. Client packages are NOT in this repo (they live in `clients/`,
which is gitignored).

## Goals
- Video in → edited video out. 9:16 1080x1920 default; 16:9 and 4:5 selectable.
- Works with ZERO API keys on a Mac (local Whisper + ffmpeg + HyperFrames). Keys are optional upgrades.
- Output quality must be "really good right off the bat": transitions + transition SFX, background
  motion graphics, background text, lower-thirds, end cards, subject-matted cards behind/in front.
- 30–40 curated style cards in a browsable local style-guide page (like Brand Nat's pack):
  categories Hook / Captions / Layout / Proof / B-roll / Signature / Motion & pace / Outro.
  Each card = sketch + 2-line description + copyable prompt. "Add to mix" → one combined prompt.
- Install path for non-technical users: download zip → drag into Claude Code → say "install this".
  Claude runs the installer itself. No terminal needed by the user.
- Onboarding questionnaire on first run → `profile/style-profile.json` (brand colors, fonts, logo,
  platform, reference links, caption style, music preference, transcription key choice).
- Reference study: watch Instagram/TikTok/YouTube links from the questionnaire without a paid
  subscription (yt-dlp + frames) and write a style summary into the profile.
- Optional add-on: Telegram. Record → send to bot → edited video comes back. Documented and scripted,
  off by default.

## Non-goals (v1)
- No carousels, no image posts. Post caption text is a "maybe" → produce `caption.txt` next to the
  export only if the profile asks for it, clearly marked as draft for human approval.
- No hosted service. Everything runs on the user's machine.
- No per-client styles baked into the public repo.

## Anti-goals (things that make it a failure even if it "works")
- Captions that are not verbatim. Spoken-word captions are never rewritten. Any generated copy
  (titles, hooks, CTAs, post captions) is flagged for approval. (a real client's viral reel drew "this is AI"
  backlash — this rule is universal.)
- Stacked effects. One signature effect per idea. Brand Nat rule.
- Leaked secrets. No tokens, keys, private paths or other clients in the repo. Check before commit.
- Generic look. Defaults must look designed: kerned type, brand palette, eased motion, ducked music.

## Folder contract (created by `reelready init`)
```
AI Video Editor/
  raw footage/     ← user drops phone clips here (read-only for the agent)
  references/      ← example videos, screenshots, links.txt (read-only)
  assets/          ← logo, fonts, music, brand.json (read-only)
  exports/         ← agent writes here only: <date>-<slug>/final.mp4, draft.mp4, edl.json, caption.txt
```
Everything else (transcripts, proxies, renders) goes in `.reelready/work/` inside the main folder.

## Pipeline (what the orchestrator skill does on "edit this")
1. Ingest: probe clips, make 720p proxies, transcribe (local Whisper default; AssemblyAI or
   ElevenLabs if a key is in the profile). Word-level timestamps required.
2. Cut: dead air, filler, retakes (yt-edit logic) → EDL. Keep the hook in the first 2 s.
3. Plan: pick styles from the mix the user chose, or the profile's default mix. Write a one-screen
   edit plan (hook, beats, b-roll cutaways, lower-third, end card, music) and SHOW it to the user.
   Wait for "go" unless the user said "just do it".
4. Render: ffmpeg for cuts/reframe/loudnorm; HyperFrames for captions, overlays, motion graphics,
   transitions; subject matting local (no key) for behind-subject effects.
5. QA: ffprobe the export (duration, 1080x1920, audio levels), extract 6 frames, look at them,
   fix obvious issues once, then deliver `final.mp4` + a 3-line summary. Never claim "done" without
   the probe.

## Engines bundled (copied from Suhaas's skills, de-branded, keys made optional)
- cut/transcribe: `video-use` repo (without .venv) with a transcription backend switch:
  `whisper-local` (faster-whisper, default) | `assemblyai` | `elevenlabs`.
- dead-air/filler: `yt-edit`.
- captions: `embedded-captions` (local Whisper + matting).
- overlays: `talking-head-recut`, `motion-graphics`, `general-video`, `media-use` (keys optional).
- HyperFrames family copied together (10 sub-skills).
- Reference study: `watch` (yt-dlp + frames; Whisper fallback uses the same backend switch).
- ffmpeg recipes from ECC video-editing as reference doc.

## Style card schema (`styles/cards/*.json`)
```json
{ "id": "H1", "category": "hook", "name": "Chunky title behind head",
  "oneliner": "Big title sits behind you; you're cut out in front.",
  "description": "2 lines max.",
  "prompt": "Natural-language instruction Claude follows when rendering.",
  "engine": "captions|overlay|cut|motion|composite",
  "needs": ["matting", "transcript", "assets:logo"],
  "pairs_with": ["C2"], "avoid_with": ["X1"], "sketch": "sketches/H1.svg" }
```

## Business model (recommendation, see docs/business-model.md)
Free kit (GitHub + "comment STYLES" on reels) → $500 Done-With-You setup → $X/mo Done-For-You via
Telegram. Founding clients: free setup in exchange for 3 intros + one storytelling reel about it.

## Left to the builder
Exact style list, SVG sketches, HTML page design, installer details, smoke-test clip.
