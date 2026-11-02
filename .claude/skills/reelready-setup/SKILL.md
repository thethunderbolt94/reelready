---
name: reelready-setup
description: ReelReady onboarding. Use on first run (no style profile yet), when the user says "install this", "set up reelready", "set me up", "redo my setup", or when doctor reports missing pieces. Installs dependencies with the user's OK, creates the "AI Video Editor" folders, runs a friendly one-question-at-a-time brand questionnaire, writes the style profile, studies their reference videos, then picks a house style for their type of business.
---

# ReelReady setup

The user is probably not technical (think: a cafe owner). Plain words, no jargon, one question
per message, short. Offer a sensible default with every question so "you pick" always works.
Use AskUserQuestion for multiple-choice questions when it is available. Run all commands yourself
from the repo root. Only ask the user to type into a terminal when something needs their password
or a secret key, and then give them exact lines to paste.

Brand name for messages: read `reelready.config.json` -> `brand.name` / `brand.by`.

## A. Check and install

First `uname -s`. `MINGW*`, `MSYS*` or `CYGWIN*` = Windows: follow `references/windows.md` and stop
here until the owner is running Claude Code inside Ubuntu.

```bash
python3 scripts/doctor.py
```
- A Mac box pops up asking to install "command line developer tools" (or `python3` prints
  `xcrun: error` / `No developer tools were found`) -> `references/install.md` section 1.
- Exit 0 -> say "Everything needed is already installed." and go to B.
- Mac and doctor shows `WARN homebrew` -> Homebrew first: `references/install.md` section 2.
- Exit 1 with MISS lines -> summarise in plain words ("I need to install a video tool and the free
  captioning engine. About 5-10 minutes and about 2 GB. OK?"). On yes, start `bash scripts/setup.sh`
  with the Bash tool's background option and go straight on to B and C while it runs. When it
  finishes, re-run doctor. FAILED lines that mention network, "could not resolve host" or timeouts:
  `references/install.md` section 4.
- `FAIL free disk space`: setup can't fix that. Say: "Your computer is almost full (<n> GB free).
  I need about 3 GB free to install and make videos. Could you empty the Trash or delete some old
  videos, then say 'try again'?" B-D can still go ahead meanwhile. `WARN` (under 3 GB): mention it
  in one line and carry on.

## B. Main folder

Run `python3 scripts/rr.py where --json` first.
- `configured` true -> don't ask where again. If `profile_exists`, ask: "Update a few answers, or
  start fresh?" **Update** -> re-ask only what they name, then D. **Start fresh** -> keep the old one
  as a backup (`mv "<profile>" "<main folder>/.reelready/style-profile.backup-<YYYY-MM-DD>.json"`,
  add `-2` if taken) and run C in full.
- Otherwise ask: "Where should your **AI Video Editor** folder live? I suggest your Desktop."
  Default `~/Desktop/AI Video Editor` (WSL: see `references/windows.md`). Then:
  ```bash
  python3 scripts/init.py --path "<chosen path>/AI Video Editor"
  ```
  If a Mac box asks to allow access to the Desktop folder, tell them to click OK.

Tell them the four folders in one line each: **raw footage** (drop clips), **references** (videos
you like), **assets** (logo, fonts, music), **exports** (finished videos appear here). Offer to open
it: `open "<path>"` (Mac), `explorer.exe "$(wslpath -w "<path>")"` (WSL), `xdg-open` (Linux).

## C. Questionnaire (one at a time, in this order)

Save after every answer so nothing is lost if they stop midway. Always use a quoted heredoc
(names like "Joe's" break `echo '...'`):
```bash
python3 scripts/rr.py profile-merge - <<'JSON'
{"business": {"name": "Joe's Bakery"}}
JSON
```
Schema: `profile/example-profile.json`. Copy its keys; never invent new top-level keys. Lists are
replaced on merge, not appended: always send the whole list.

1. **Business name** -> `business.name`.
2. **What you do.** "In a few words, what do you do? (e.g. family bakery, sourdough and cakes)" ->
   `business.what_we_do`. Needed: it picks their house style in F. If they shrug, offer the
   `label`s from `styles/presets.json` as choices and save the label they pick.
3. **Where.** "What town or area are you in? (for local hashtags; skip is fine)" -> `business.location`.
4. **Where do you post, and your @handle there?** Instagram Reels / TikTok / YouTube Shorts ->
   `aspect` 9:16, `resolution` 1080x1920. YouTube (wide) -> 16:9 1920x1080. Instagram feed -> 4:5
   1080x1350. Several -> the vertical one wins. `platforms` list from: `instagram-reels`, `tiktok`,
   `youtube-shorts`, `youtube`, `instagram-feed`. Handle -> `business.handle` (skip is fine).
5. **Logo.** "Drag your logo into the assets folder (PNG with a see-through background is best),
   or tell me where it is." Dragged in -> `ls "<assets>"` to find it. Given a path -> ask before
   copying it into assets/ as `logo.<ext>` (never overwrite). Save `brand.logo: "assets/<file name>"`
   (relative to the main folder). No logo -> `brand.logo: null`; end cards use the business name.
6. **Brand colors.** "Do you have brand colors? Tell me (names or hex codes are fine), say 'pull
   them from my logo', or say 'you pick'."
   - Logo: `python3 scripts/rr.py palette "<main folder>/<brand.logo>"` (needs ffmpeg; if setup is
     still running, say "I'll pull them from your logo once the install finishes" and do it before
     D). Skip near-white and near-black swatches (usually the logo's background). Show the rest as
     hex + a plain name ("deep green #2F4B3A") and confirm.
   - "You pick": primary `#1F2A30`, secondary `#F4EFE6`, accent `#E2603A`, text `#FFFFFF`,
     background `#141414`.
   - Fill `brand.colors` primary/secondary/accent/text/background (text must contrast with
     background: white or near-black). `brand.colors_source`: manual | logo | default.
7. **Fonts.** "Got brand fonts? Drop the .ttf/.otf files in assets/fonts. Otherwise I'll use a
   clean, bold pair that looks great on phones." Default: `brand.fonts` heading `Archivo Black`,
   body `Inter`, `source: "default"`, `files: []`. With files: `files: ["assets/fonts/<file>"]`
   (heading font first), `source: "files"`, and `heading` = the font's real family name:
   `python3 scripts/rr.py run -- python -c 'import sys; from PIL import ImageFont; print(ImageFont.truetype(sys.argv[1]).getname()[0])' "<main folder>/assets/fonts/<file>"`
   (if that fails, ask them the font's name).
8. **Caption look.** Read each option's `name` and `oneliner` from `styles/cards/<ID>.json` and
   offer: **You pick: matched to your business** (default) / C1 / C3 / C6 ("or say 'more' for C2, C4,
   C5"). Default -> `captions.look: "house"`, `captions.card: null` (the house style in F picks it).
   A card -> `captions.card: "<ID>"`, `captions.look: "<card name>"`. Then tell them (no question):
   "Captions always use your exact words. We never rewrite what you say." `captions.verbatim: true`.
9. **Music.** "No music (you add a trending sound in the app when posting; recommended)" / "My own
   track (drop it in assets/music)". Only music they own or have a licence for. Save
   `music.preference` `"none"` or `"my-own"`, `music.file` `"assets/music/<file>"` or null. "My own"
   but no file yet -> save `"none"` for now and say "Drop a track in assets/music any time and say
   'use my music'."
10. **Call to action.** "What should people do after watching? (Visit us / Book via the link in bio
    / Call us / DM us)" -> `copy.cta`. Default by business: walk-in -> "Visit us", bookings ->
    "Book via the link in bio", trades -> "Call us".
11. **Reference videos.** "Paste 2-5 links to Reels, TikToks or YouTube videos whose LOOK you love
    (yours or anyone's), or drop video files in the references folder. Or skip for now." Save
    `references` as `[{url, note}]`; append to `references/links.txt` only if they ask
    (references/ is read-only otherwise).
12. **Tone.** "Three words for how your videos should feel?" (e.g. warm, playful, calm) -> `tone`
    (list). Default: warm, friendly, local.
13. **Post text.** "Want me to also draft the text for your post (caption + hashtags) each time?
    It's always marked as a draft for you to check." -> `post_caption.draft` and `copy.auto` (same
    true/false), `post_caption.hashtags: true`.

Transcription is not a question: save `transcription: {"backend": "whisper-local", "key_stored": false}`
(free, on their computer). If they ever mention a paid transcription key: `references/keys.md`.

Finish the profile: `rules` block from the example (all true). `default_mix` and `house_style` are
filled in F; never finish setup with an empty `default_mix`.

## D. Confirm

Show a 6-line recap (business, format, colors, fonts, caption look, music) and ask "Look right?"
Fix anything they change.

## E. Study references

If `references` is non-empty or references/ has videos: invoke **reelready-study** (it knows it was
called from setup and leaves `default_mix` to F). Failures there never block setup.

## F. House style

Gives every owner their own starting look instead of one template for everyone.
```bash
python3 scripts/rr.py house-style --profile "<profile>" --apply
```
It matches `business.what_we_do` + `business.name` to a type in `styles/presets.json` and writes
`default_mix` + `house_style` (a chosen `captions.card` replaces the preset's; null keeps it).
- Output `note` says "Kept your existing default_mix" -> their profile already had a mix. Show the
  profile's current mix (names from `styles/cards`) and ask "Keep your current style, or switch to
  the <label> one?" Switch -> re-run with `--force`.
- Otherwise show it in plain words: "You look like a **<label>**. Your house style: <each card in
  `cards`: name - oneliner>. Each reel also gets one big move, taking turns: <`signature_cards`
  names>. Sound: <S card name>." `matched_by` `fallback` -> add "I couldn't tell your type, so I
  started neutral."

Ask ONE question: "Keep this, or want it calmer / punchier / different?"
- **Keep** -> done.
- **Calmer** -> S card one step calmer on `sound_scale` in presets.json, hook -> the first (quietest)
  H on `hook_scale` that clashes with nothing in the mix or the signature list (`avoid_with`). Already
  the calmest -> say so and offer **different**.
- **Punchier** -> S card -> `S2`, hook -> the boldest H on `hook_scale` that clashes with nothing.
- **Different** -> show the 2 types in `alternatives` the same way (one line each); on a pick:
  `python3 scripts/rr.py house-style --profile "<profile>" --type "<type>" --apply --force`.

Calmer/punchier: save the whole edited list (heredoc as in C, `{"default_mix": [...]}`) and re-show
only the changed cards. Never leave `default_mix` empty. On a later "update" where `what_we_do`
changed, offer the new type and apply with `--force` only on yes.

## G. Ready message (exactly 5 lines)

```
You're set up. <brand.name> knows your brand now.
1. Drop a clip in: <main folder>/raw footage
2. Tell me: edit this
3. I'll show you a quick plan, then make the video.
4. Finished videos land in: <main folder>/exports
```
Optional extra line: "Want to browse the 30+ styles first? Say: show me the styles."
