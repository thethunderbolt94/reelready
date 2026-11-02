# Attribution: bundled skills

ReelReady ships copies of the skills below so the kit works offline and stays pinned to a known-good version.
We changed them only to (a) remove private paths and personal notes, (b) make every API key optional with a
local default, and (c) replace "update this skill" prompts with a note that the skills are bundled. Original
license files and notices are kept in each folder; where an Apache-2.0 upstream folder shipped without the
license text, a copy was added as `LICENSE` so every folder is self-describing.

| Skill folder | Origin | License | ReelReady changes |
| --- | --- | --- | --- |
| `hyperframes` | HeyGen HyperFrames skills (https://github.com/heygen-com/hyperframes), installed via `npx hyperframes skills` | Apache-2.0 (HyperFrames project) | Bundled note replaces the plugin/update preamble; routing reads bundled workflows from `.claude/skills/`; non-bundled workflows need the user's OK before install; `references/skill-lifecycle.md` and `references/capability-menu.md` point at the bundled copies |
| `hyperframes-core`, `hyperframes-cli`, `hyperframes-animation`, `hyperframes-creative`, `hyperframes-audio`, `hyperframes-registry`, `hyperframes-keyframes`, `hyperframes-studio` | HeyGen HyperFrames domain skills (same source) | Apache-2.0 | Bundled note replaces the plugin/update preamble |
| `embedded-captions` | HeyGen HyperFrames workflow skill | Apache-2.0 | Bundled note; "keep this skill fresh" prompt removed; `init` runs with `HYPERFRAMES_SKIP_SKILLS=1` |
| `talking-head-recut` | HeyGen HyperFrames workflow skill, itself adapted from vtake-skills (https://github.com/notedit/vtake-skills) | Apache-2.0 / MIT (see `NOTICE.md`, kept) | Bundled note; "keep this skill fresh" prompt removed |
| `motion-graphics` | HeyGen HyperFrames workflow skill | Apache-2.0 | Bundled note; "keep this skill fresh" prompt removed (its `GEMINI_API_KEY` was already optional) |
| `general-video` | HeyGen HyperFrames workflow skill | Apache-2.0 | Bundled note; update step removed; borrowing limited to bundled workflows |
| `media-use` | HeyGen HyperFrames media skill | Apache-2.0; the bundled SFX were replaced by sounds synthesised by `engines/make_sfx.py` (MIT, `audio/assets/sfx/CREDITS.md`) | New "no-key mode" section: `--local-only`, bundled SFX, user-supplied music/images in `assets/`, local transcription; HeyGen sign-in is an optional upgrade |
| `hyperframes-helper` | Community helper kit for HyperFrames, from the kit author's skill library (no upstream license file shipped) | Unknown upstream; check before redistributing | Copied as is (its sample `smoke-test.mp4` left out) |
| `watch` | claude-video by Bradley Bonanno (https://github.com/bradautomates/claude-video) | MIT (`LICENSE`, kept) | Whisper fallback now prefers ReelReady's local `engines/transcribe.py` (faster-whisper, no key); `--whisper local|assemblyai|groq|openai`; setup treats the local engine as "ready"; private notes removed. `~/.config/watch/.env` stays optional |
| `yt-edit` | The kit author's own skill (dead-air / filler / retake EDL, `deadair.py`) | Same license as ReelReady | Copied as is; its logic is reused by `engines/cut.py` |

Also vendored outside this folder: `engines/video-use/` is video-use by Browser Use
(https://github.com/browser-use/video-use, MIT, `LICENSE` kept) without its `.venv`, `.git` and `.env`;
`helpers/transcribe.py` now works without an ElevenLabs key. The ffmpeg recipe reference in
`docs/engines.md` adapts the `video-editing` skill from everything-claude-code (ECC).
