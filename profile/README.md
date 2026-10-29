# Style profile

Your brand, written once during setup, read by every edit.

- **Lives at** `<main folder>/.reelready/style-profile.json` (on your computer, not in this repo).
- **Schema:** [`example-profile.json`](example-profile.json) (a made-up cafe). Copy its keys.
- **Written by** the `reelready-setup` skill (questionnaire) and `reelready-study` (adds
  `reference_style`). Edit by hand or say "change my brand colors".
- **Merged with** `python3 scripts/rr.py profile-merge -` (JSON on stdin, deep merge, stamps `updated`).

| Key | Meaning |
|---|---|
| `business` | name, handle, one line on what you do |
| `platforms`, `aspect`, `resolution` | where you post; 9:16 1080x1920 default |
| `brand.colors` | primary, secondary, accent, text, background (hex) |
| `brand.logo`, `brand.fonts` | paths relative to the main folder; fonts default to Archivo Black + Inter |
| `captions` | `look` (clean-pill, bold-pop, karaoke, quiet-subtitle), matching style `card`, `verbatim` always true |
| `music` | none, my-own, calm, upbeat; ducked -18 dB under speech |
| `tone` | three feel words |
| `references` | links/files the user admires |
| `reference_style` | what the study found: caption style, pacing, color, hooks, music, effects, do-not-copy, summary |
| `post_caption.draft` | write `caption.txt` (always marked DRAFT) |
| `copy.auto` | optional; true = write `post.md` (hooks, caption, CTA, hashtags) after every edit via `reelready-copy`; false = only when asked ("write the post for this") |
| `copy.cta` | your usual call to action ("Visit us", "Book via link in bio", "DM us"); shaped to each reel, never adds offers or hours |
| `copy.hashtags_extra` | tags you always want (e.g. your own branded tag); counted in the 5-8 |
| `transcription` | `backend` (whisper-local, assemblyai, elevenlabs) and whether a key is stored. Never the key itself |
| `default_mix` | favourite style card IDs; empty = editor picks hook + captions + lower-third + end card |
| `rules` | verbatim captions, generated copy needs approval, one signature effect (always true) |

API keys never go in the profile. They live in `<main folder>/.reelready/.env`.
