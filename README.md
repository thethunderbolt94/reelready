# ReelReady by Thrive Labs

**Drop a clip. Get a reel.**

ReelReady turns the videos you film on your phone into edited, captioned, on-brand reels, right
on your own computer. It's a free kit for Claude Code: you talk to Claude, Claude does the editing.

- Cuts the pauses, the "um"s and the retakes
- Adds captions that match your words exactly
- Adds your colors, your logo, titles, lower-thirds, an end card and music
- Hands back a 9:16 video ready for Instagram, TikTok or YouTube Shorts

## Get started (no tech skills needed)

1. **Download the zip** (green "Code" button -> Download ZIP) and unzip it.
2. **Open Claude Code**: the **Code** tab in the Claude desktop app.
3. **Drag the folder in** and say: **install this**
   Claude installs what's needed, asks you a few easy questions about your brand (name, colors,
   logo, the look you like) and makes an **AI Video Editor** folder on your Desktop.
4. **Drop a clip in `raw footage`** and say: **edit this**
   Claude shows you a quick plan, you say "go", and the finished video appears in `exports`.

That's it. First install takes about 10 minutes (it downloads a free captioning engine once).
You need about **3 GB of free space** on your computer; Claude tells you if it's too full.

## Your folder

```
AI Video Editor/
  raw footage/   <- drop your phone clips here (never changed or deleted)
  references/    <- videos you love the look of, or links in links.txt
  assets/        <- logo, fonts/, music/, sfx/
  exports/       <- finished videos appear here
     2026-10-28-latte-art/
        final.mp4     ready to post
        draft.mp4     clean cut, before graphics
        plan.md       the plan you approved
        caption.txt   draft post text (only if you asked; always check it)
```

## Things you can say

| Say | What happens |
|---|---|
| edit this / edit the newest clip | edits the newest video in raw footage (shows you the plan first) |
| edit these 3 clips | talking clip + b-roll shots cut together |
| use styles H1+C2 / use the Cafe story mix | edits with exactly those styles |
| show me the styles | opens the style guide in your browser |
| make it 16:9 for YouTube | wide version of the same edit |
| study my references | learns the look of videos you like |
| change my brand colors | updates your setup |

## Zero keys, zero subscriptions

Everything works with **no API keys** and no accounts: your words are turned into captions on your
own computer, and the editing happens there too. Your videos never leave your computer unless you
choose one of the optional cloud upgrades below. (Under the hood: Whisper, ffmpeg, HyperFrames, yt-dlp.)

### Optional upgrades

| Key | What it adds | Where it goes |
|---|---|---|
| AssemblyAI | slightly better transcription on noisy audio | paste it during setup |
| ElevenLabs | alternative cloud transcription (Scribe) | paste it during setup |

Keys are saved privately in `AI Video Editor/.reelready/.env` on your computer. Never in this
folder, never shown back to you.

## Styles

30+ hand-picked style cards (Hook, Captions, Layout, Proof, B-roll, Signature, Motion & pace,
Outro), each with a sketch, a two-line description and a copyable prompt. Mix a few, copy the
combined prompt, and say "use styles ...". Say **show me the styles** to open the
[style guide](styleguide/) (runs locally at `http://localhost:4810`).

Rules every edit follows: captions are word-for-word, any text Claude writes is marked for your
approval, and only one big effect per moment, so nothing looks "AI".

## Telegram (optional)

Record on your phone, send it to your own Telegram bot, get the edited reel back. Off by default.
See [addons/telegram/README.md](addons/telegram/README.md).

## For developers

- Manual install and troubleshooting: [INSTALL.md](INSTALL.md)
- How it fits together: [docs/architecture.md](docs/architecture.md)
- Agent brief Claude reads: [CLAUDE.md](CLAUDE.md); skills in `.claude/skills/reelready-*`
- Engines (`engines/`, contracts in [engines/README.md](engines/README.md)): `transcribe.py`, `cut.py`,
  `render_cut.py`, `qa.py`, plus `captions.py` (fast verbatim burn-in); stdlib + a repo-local `.venv`
- Helpers: `scripts/doctor.py` (dependency + free-disk table, exit code), `scripts/setup.sh`
  (idempotent, no sudo), `scripts/init.py --path` (folder contract), `scripts/rr.py` (paths, jobs,
  keys, profile, music ducking, multi-clip `join-drafts`)
- Smoke test: `bash tests/smoke/run.sh` (needs macOS `say`; exits 1 on any failed step)
- Rename the brand in one place: `reelready.config.json`
- Style profile schema: [profile/example-profile.json](profile/example-profile.json); the real one
  lives at `<main folder>/.reelready/style-profile.json`
- Bundled third-party skills and their licenses: [.claude/skills/ATTRIBUTION.md](.claude/skills/ATTRIBUTION.md).
  **Check before public release:** `hyperframes-helper` has no upstream LICENSE file (get the
  author's permission or drop it), and the Apache-2.0 HyperFrames skill folders ship without a copy
  of the license text (add one).

Requirements: macOS (Apple Silicon or Intel) with Homebrew; Linux best-effort; Windows via WSL2.

MIT licensed. See [LICENSE](LICENSE).

---

ReelReady is free. Thrive Labs sets it up for you, tunes your style, and runs it for you ->
[thrivelabs.ai](https://thrivelabs.ai)
