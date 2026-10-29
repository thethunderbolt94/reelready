---
name: reelready-setup
description: ReelReady onboarding. Use on first run (no style profile yet), when the user says "install this", "set up reelready", "set me up", "redo my setup", or when doctor reports missing pieces. Installs dependencies with the user's OK, creates the "AI Video Editor" folders, runs a friendly one-question-at-a-time brand questionnaire, writes the style profile, then studies their reference videos.
---

# ReelReady setup

The user is probably not technical (think: a cafe owner). Plain words, no jargon, one question
per message, short. Offer a sensible default with every question so "you pick" always works.
Use AskUserQuestion for multiple-choice questions when it is available. Run all commands yourself
from the repo root; never ask the user to open a terminal unless something truly needs their
password (Homebrew), and then give them one line to paste.

Brand name for messages: read `reelready.config.json` -> `brand.name` / `brand.by`.

## A. Check and install

```bash
python3 scripts/doctor.py
```
- Exit 0 -> say "Everything needed is already installed." and go to B.
- Exit 1 -> summarise the MISS lines in plain words ("I need to install a video tool (ffmpeg) and
  the free captioning engine. About 5-10 minutes, around 1 GB. OK?"). On yes:
  `bash scripts/setup.sh` (long; run in the background if it may pass 2 minutes, then check).
  Re-run doctor. Homebrew missing on a Mac -> the user must install it themselves (it asks for their
  Mac password): give them the one line from https://brew.sh, wait, run setup again.
- Windows: setup.sh prints WSL instructions; relay them simply.
- `FAIL free disk space` (under 1.5 GB free): setup can't fix that and the install itself needs about
  1.7 GB. Say: "Your computer is almost full (<n> GB free). I need about 3 GB free to install and make
  videos. Could you empty the Trash or delete some old files, then say 'try again'?" You can still do
  B-D (folder + questions) meanwhile; install and edit once there's room. `WARN` (under 3 GB): mention
  it in one line and carry on.

## B. Main folder

Ask: "Where should your **AI Video Editor** folder live? I suggest your Desktop." Default
`~/Desktop/AI Video Editor`. Then:
```bash
python3 scripts/init.py --path "<chosen path>/AI Video Editor"
```
Tell them the four folders in one line each: **raw footage** (drop clips), **references** (videos
you like), **assets** (logo, fonts, music), **exports** (finished videos appear here). Offer to
open it: `open "<path>"` (macOS).

If a profile already exists (`python3 scripts/rr.py where --json` -> `profile_exists`), ask:
"Update a few answers, or start fresh?" and only re-ask what they want to change.

## C. Questionnaire (one at a time, in this order)

Save as you go so nothing is lost if they stop midway:
`echo '<json fragment>' | python3 scripts/rr.py profile-merge -`
Schema: `profile/example-profile.json`. Copy its keys; never invent new top-level keys.

1. **Business name** -> `business.name`. Also ask casually for their handle and one line on what
   they do (`business.handle`, `business.what_we_do`); skip if they shrug.
2. **Where do you post?** Instagram Reels / TikTok / YouTube Shorts -> `aspect` 9:16,
   `resolution` 1080x1920. YouTube (wide) -> 16:9 1920x1080. Instagram feed -> 4:5 1080x1350.
   Several -> the vertical one wins. Save `platforms` as a list.
3. **Logo.** "Drag your logo into the assets folder (PNG with a see-through background is best),
   or tell me where it is." If they give a path, ask before copying it into assets/ as `logo.<ext>`
   (never overwrite). No logo -> `brand.logo: null`, end cards use the business name as type.
4. **Brand colors.** "Do you have brand colors? Tell me (names or hex codes are fine), or say
   'pull them from my logo'." Logo route: `python3 scripts/rr.py palette "<logo>"` and show the
   swatches as hex + a plain name ("deep green #2F4B3A"); confirm. Fill `brand.colors`
   primary/secondary/accent/text/background (text must contrast with background: white or near-black).
   `brand.colors_source`: manual | logo | default.
5. **Fonts.** "Got brand fonts? Drop the .ttf/.otf files in assets/fonts. Otherwise I'll use a
   clean, bold pair that looks great on phones." Default: heading `Archivo Black`, body `Inter`.
   Save `brand.fonts` (+ `files` list when they add files).
6. **Caption look.** Describe four, let them pick (save `captions.look`):
   - **Clean pill**: 2-4 words at a time in a soft rounded box in your brand color, lower on screen.
   - **Bold pop**: big chunky words that pop in one by one, centered; the key word in your accent color.
   - **Karaoke**: the whole line shows, and each word lights up in your color as you say it.
   - **Quiet subtitle**: small, elegant sentence-case line at the bottom; for calm, aesthetic videos.
   Then set `captions.card`: bold-pop -> `C1`, karaoke -> `C3`, clean-pill -> `C4`,
   quiet-subtitle -> `C6` (check the card exists in `styles/cards/`; else the closest captions card,
   or null if there are no cards). Ask: "One more: should
   captions always match your words exactly? (Yes - we never rewrite what you say.)" It is always
   true; the question just reassures them.
7. **Music.** None (I'll add trending audio in the app) / My own tracks (drop them in assets/music) /
   Calm bed / Upbeat bed. Mention: trending sounds are best added inside Instagram/TikTok at posting
   time; only use music they own or have a licence for. Save `music.preference`, `music.file`.
8. **Reference videos.** "Paste 2-5 links to Reels, TikToks or YouTube videos whose LOOK you love
   (yours or anyone's). Or drop video files in the references folder." Save `references` as
   `[{url, note}]`; also append the links to `references/links.txt` only if the user asks you to
   (references/ is read-only otherwise).
9. **Tone.** "Three words for how your videos should feel?" (e.g. warm, playful, calm) -> `tone`.
10. **Post captions.** "Want me to also draft the text for your post (caption + hashtags)? It's
    always marked as a draft for you to check." -> `post_caption.draft` true/false.
11. **Transcription.** "Captions are made on your computer for free. If you already pay for
    AssemblyAI or ElevenLabs you can paste a key for slightly better accuracy. Free (recommended),
    AssemblyAI, or ElevenLabs?"
    - Free -> `transcription.backend: "whisper-local"`.
    - Key -> have them paste it, then save it WITHOUT echoing it:
      `printf '%s' '<key>' | python3 scripts/rr.py set-key assemblyai` (or `elevenlabs`).
      Reply only "Saved privately on your computer." Never repeat, log, or write the key anywhere
      else (not the profile, not plan files, not the repo). Save `transcription.backend` and
      `transcription.key_stored: true`.

Finish the profile: `rules` block from the example (all true), `schema_version: 1`. `default_mix`
and `house_style` are filled in F; never finish setup with an empty `default_mix`.

## D. Confirm

Show a 6-line recap (business, format, colors, fonts, caption look, music) and ask "Look right?"
Fix anything they change.

## E. Study references

If `references` is non-empty or references/ has videos: invoke **reelready-study**. It writes
`reference_style` into the profile and shows a short summary. Failures there never block setup.

## F. House style

Gives every owner their own starting look instead of one template for everyone.
```bash
python3 scripts/rr.py house-style --profile "<profile>" --apply
```
It matches `business.what_we_do` + `business.name` to a type in `styles/presets.json` and writes
`default_mix` + `house_style` (keeps their chosen caption card). Show it in plain words, e.g.:
"You look like a **<label>**. Your house style: <each card in `cards`: name - oneliner>. Each reel
also gets one big move, taking turns: <`signature_cards` names>. Sound: <S card name>." If
`matched_by` is `fallback`, say "I couldn't tell your type, so I started neutral."

Ask ONE question: "Keep this, or want it calmer / punchier / different?"
- **Keep** -> done.
- **Calmer** -> S card one step calmer on `sound_scale` in presets.json, hook -> the first (quietest)
  H on `hook_scale` that clashes with nothing in the mix or the signature list (`avoid_with`).
- **Punchier** -> S card -> `S2`, hook -> the boldest H on `hook_scale` that clashes with nothing.
- **Different** -> show the 2 types in `alternatives` the same way (one line each); on a pick:
  `python3 scripts/rr.py house-style --profile "<profile>" --type "<type>" --apply --force`.
Calmer/punchier: save the edited list with `echo '{"default_mix": [...]}' | python3 scripts/rr.py profile-merge -`
and re-show only the changed cards. Never leave `default_mix` empty.

## G. Ready message (exactly 5 lines)

```
You're set up. <brand.name> knows your brand now.
1. Drop a clip in: <main folder>/raw footage
2. Tell me: edit this
3. I'll show you a quick plan, then make the video.
4. Finished videos land in: <main folder>/exports
```
Optional extra line: "Want to browse the 30+ styles first? Say: show me the styles."
