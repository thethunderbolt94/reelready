---
name: reelready-edit
description: ReelReady orchestrator. Turns phone clips in "raw footage" into a cut, captioned, branded reel in exports/. Use when the user says "edit this", "edit the newest clip", "edit these", "make a reel", "use styles H1+C2", "use the Cafe story mix", pastes a prompt from the style guide ("Edit the newest clip in raw footage. Use styles: ..."), or drops a video and asks for an edit. Runs ingest, cut, plan (shown for approval), render, QA.
---

# ReelReady edit

Run every command from the repo root. Hard rules in CLAUDE.md apply to every step (verbatim
captions, generated copy flagged, one signature effect, write only to exports/ and .reelready/work/).

Engines run through the helper so the repo `.venv` and the user's private `.env` are picked up:
`python3 scripts/rr.py run -- python3 engines/<engine>.py ...`. Never print key values.

## 0. Preflight (silent when fine)

```bash
python3 scripts/rr.py where --json
```
- `configured` false or `profile_exists` false -> invoke **reelready-setup** first, then come back.
- First edit this session: `python3 scripts/doctor.py --fast`. Exit 1 -> look at which line failed:
  - `MISS` (a tool is missing): tell the user in one line what is missing, get their OK, run
    `bash scripts/setup.sh`, re-run doctor.
  - `FAIL free disk space` (under 1.5 GB free; HyperFrames refuses to render under 1 GB): do NOT run
    setup. Say: "Your computer is almost out of space (<n> GB free). Making the video needs at least
    1.5 GB, ideally 3 GB. Empty the Trash or delete some old videos, then say 'try again'." Offer once
    to clear old ReelReady scratch: list the folders in `<main folder>/.reelready/work/` with sizes and
    delete only the ones they OK (never anything in raw footage, references, assets or exports).
    Re-run doctor before rendering. The same applies if a render stops with "disk is almost full".
  - `WARN free disk space` (under 3 GB): carry on; mention it in one line if the clip is long or 4K.
- Read the profile (`profile` path from `where --json`, i.e. `<main folder>/.reelready/style-profile.json`)
  and `reelready.config.json` (brand + defaults).

## 1. Resolve the input

| User says | Clips |
|---|---|
| "edit this" + a dragged/pasted path | that file (copying it into raw footage is optional; never move it) |
| "edit this" / "edit the newest clip" with no path | `python3 scripts/rr.py newest` |
| "edit these" / "the last 3 clips" | `python3 scripts/rr.py newest --n 3` |
| names a file | find it under raw footage |

Say which file(s) you picked in one line. Probe each:
`ffprobe -v error -show_entries format=duration:stream=codec_type,width,height,r_frame_rate,side_data_list -of json "<clip>"`
(note rotation side data: phone clips are often stored landscape + rotate 90).

**Script hand-off (check before creating the job).** If an export folder from the last 14 days has
`script.md` (or `script-v2.md`) and no `final.mp4`, list up to 3, newest first, by script title and ask
once: "Is this clip for one of your scripts?" with "none" as an option. On a pick: reuse that folder
(do NOT call `export-dir`; its `work_dir` is `.reelready/work/<same folder name>/`), and read the script.
The folder keeps the script's date; plan.md notes today as the filming date. On "none", or no match,
carry on below.

Create the job: `python3 scripts/rr.py export-dir "<3-5 word slug from topic or filename>"` ->
gives `export_dir` (exports/<YYYY-MM-DD>-<slug>/) and `work_dir` (.reelready/work/<same>/).
All intermediates go in `work_dir`.

**Multi-clip roles.** Classify each clip: *A-roll* (someone talking; transcript has words) or
*b-roll* (no/little speech: product, space, hands). Ask only if unclear.
- A-roll drives the timeline and the audio. B-roll is laid OVER the A-roll as cutaways (A-roll
  audio keeps playing), 1.5-3 s each, placed on lines that describe what the b-roll shows.
- Several A-roll clips: the EDL is single-source, so run step 2 once per A-roll clip with numbered
  files (`transcript_01.json`, `edl_01.json`, `draft_01.mp4`; render_cut then writes
  `draft_01.words.json` next to it). Use `--keep-hook-seconds 2` for the first clip only, `0` for the
  rest. Then join them in spoken order (stream copy, words shifted onto the joined timeline):
  `python3 scripts/rr.py join-drafts "$W/draft.mp4" "$W/draft_01.mp4" "$W/draft_02.mp4"`
  -> `$W/draft.mp4` + `$W/draft.words.json`. Everything after this uses those two files.

## 2. Ingest + cut

```bash
W="<work_dir>"; C="<clip>"
# optional preview proxy for long or 4K clips (frame looks only; renders use the original)
ffmpeg -v error -y -i "$C" -vf "scale=-2:720" -c:v libx264 -preset veryfast -crf 28 -c:a aac "$W/proxy.mp4"
python3 scripts/rr.py run -- python3 engines/transcribe.py "$C" --out "$W/transcript.json" --backend <profile.transcription.backend>
python3 scripts/rr.py run -- python3 engines/cut.py "$C" --transcript "$W/transcript.json" --out "$W/edl.json" --keep-hook-seconds 2
python3 scripts/rr.py run -- python3 engines/render_cut.py --edl "$W/edl.json" --transcript "$W/transcript.json" --out "$W/draft.mp4" --aspect <aspect> --fps 30
```
- Cloud backend fails (bad key, no network) -> say so in one line, retry with `whisper-local`.
- `render_cut.py` also writes `<out without .mp4>.words.json` (here `$W/draft.words.json`): words
  re-timed to the draft. Captions use THAT, never the source-timed transcript. It needs `--transcript`.
- Loudness is handled here once: render_cut normalises to -16 LUFS (true peak -1.5 dBTP). Later steps
  keep the draft's audio (captions.py copies it bit-exact) or re-normalise to the same target (music mix).
- Read `edl.json` `removed` + `stats` for the plan ("removed 14 s: dead air 8 s, 4 fillers, 1 retake").
- Look at 3 frames of the draft (`ffmpeg -ss T -i draft.mp4 -frames:v 1 -vf scale=512:-2 f.jpg`, Read)
  so the plan is grounded in what is on screen (where the face is, empty space for text).

**Aspect.** Use the user's ask, else `profile.aspect`, else config default. Sizes: 9:16 1080x1920,
16:9 1920x1080, 4:5 1080x1350. A landscape clip going to 9:16 is center-cropped by render_cut; if
the subject is off-center in the frames, say so in the plan and offer a "fit with blurred
background" alternative (`split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30[bg];[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2`).

## 2.5 Story pass (talking-to-camera clips over ~12 s; skip for single takes under ~10 s)

The owner's order is rarely the order that holds a stranger. Fix ORDER and SELECTION only; never
write a line. Full rules and the four structures: `references/story.md`.

```bash
python3 scripts/rr.py run -- python3 engines/story.py --edl "$W/edl.json" --transcript "$W/transcript.json" --list
python3 scripts/rr.py run -- python3 engines/story.py --edl "$W/edl.json" --transcript "$W/transcript.json" --order 3,0,1,2 --drop 4 --out "$W/edl.story.json"
python3 scripts/rr.py run -- python3 engines/render_cut.py --edl "$W/edl.story.json" --transcript "$W/transcript.json" --out "$W/draft.mp4" --aspect <aspect> --fps 30
```
- Hook sentence first: the most specific line (a number, a name, a surprise), never the greeting.
- Reorder across sentence boundaries only; max 2 moves under 30 s; one structure per reel.
- The plan shows the new order as the owner's own sentences and names what was dropped and why.
- "keep it as I said it" -> skip this step and render from `edl.json`.
- With a picked script: its `structure:` is the default structure here, and its hook line points to the
  hook sentence (closest spoken match in the transcript). Captions stay verbatim from what was said on
  film, never from the script. If they went off-script, the reel shows what they said.

## 3. Plan and show

**Pick the mix.** The result is always a list of card IDs; every ID is loaded from
`styles/cards/<ID>.json` and its `prompt` is used verbatim.
1. User named styles ("use styles H1+C2", "H1, C2 and O3"), or pasted a prompt from the style guide /
   **reelready-styles** (starts `Edit the newest clip in raw footage. Use styles: H1 + C1 + O1.` or
   `Use style: H1.` for one card): take the IDs from that line; split on `+`, `,`, `and`, spaces;
   uppercase. Unknown ID -> list the closest IDs from that category and ask. "Show me the plan first"
   in the prompt is the normal behaviour (step 3 always shows the plan).
2. User named a ready-made mix ("use the Cafe story mix", "Listing tour"): match `name` in
   `styles/mixes.json` (case-insensitive), take its `ids`.
3. Else `profile.default_mix` if non-empty.
4. Else the house style: `python3 scripts/rr.py house-style --profile <profile> --apply`, use its
   `default_mix`, and say in one line "No house style yet, so I picked the <label> one."
5. Else (no presets.json) default: one **hook** card + the **captions** card (`profile.captions.card`,
   else the first captions card) + one **lower-third** (card whose name/oneliner mentions "lower third") + one
   **end card** (first `outro` card). If styles/cards is missing: built-in equivalents (big hook
   title 0-2 s, word-chunk captions, name lower-third, logo end card).

**Rotate the signature** (steps 3-4 only; user-named IDs or mixes stay as given):
`python3 scripts/rr.py next-signature` -> this reel's big move (prints nothing = skip). If the mix
holds a card from `house_style.signature`, swap it for this one; else add it. If it clashes with the
mix (`avoid_with`), skip it this reel and say why. After "go": `next-signature --commit` (re-edits
of this reel keep its signature; don't call it again).

**Fill the brand tokens** in each card prompt from the profile: `{{brand.primary}}` ->
`brand.colors.primary`, `{{brand.accent}}` -> `brand.colors.accent`, `{{font.display}}` ->
`brand.fonts.heading`, `{{font.body}}` -> `brand.fonts.body`. Missing value -> the kit default
(Archivo Black / Inter; never guess a brand color).

**Check the mix.** Drop or swap anything in another card's `avoid_with`. At most ONE signature
effect (category `signature`, or any behind-subject / big-motion card) per idea; if the user stacked
two, keep the first, say why in one line. Every `needs` entry must be met (`assets:logo` -> logo
file exists; `matting` -> local matting via the captions/composite skill; `transcript` -> done).

**Write the plan** to `<export_dir>/plan.md` and show it (one screen, this exact shape):

```
EDIT PLAN: <slug>                                  <brand.name>
Clip       raw footage/<file>  (<dur>, <WxH>)  [+ b-roll: <files>]
Cut        <src dur> -> ~<new dur>   removed <s>: dead air <s>, <n> fillers, <n> retakes
Format     <aspect> <WxH> @30fps
Script     <title>, followed | changed                     (only when a script was picked)
Hook 0-2s  says: "<first spoken words, verbatim>"
           card <ID> <name>: "<TITLE TEXT>"                 [GENERATED - approve?]
Beats      0:00 hook / 0:0x <beat> / 0:1x <beat> / 0:2x CTA
B-roll     <file> at 0:12-0:15 over "<words>"   (or: none)
Captions   <ID> <name>: verbatim, <font>, <colors>, max <n> words/line
Lower 3rd  <ID> 0:02-0:06 "<Business> · <descriptor>"      [GENERATED - approve?]
End card   <ID> logo + "<CTA>"                             [GENERATED - approve?]
Music      <file | none>: -18 dB under speech, 0.5 s in / 1.5 s out
Signature  <ID> <name> (this reel's one big move; last reel: <last_signature name | none>)
Post copy  caption.txt draft                               [GENERATED - approve?]   (only if profile asks)
Output     exports/<slug>/final.mp4

## Brand choices   (3+ bullets; each names a brand hex, a brand font, "logo" or a reference_style phrase; 2+ hexes overall)
- Hook <H card> title in <brand.fonts.heading>, <secondary hex> on <primary hex>, behind the subject
- Captions <C card> in the brand font, key word in accent <accent hex>, 2-3 word chunks, lower third
- Pacing from the references: <reference_style.pacing, quoted>
- End card <O card>: logo on <primary hex>, CTA in <brand.fonts.body>
Reply "go", or tell me what to change.
```
Every line of words you wrote (not spoken) carries `[GENERATED - approve?]`. Wait for "go"
unless the user said "just do it" / "no need to check". Apply changes, re-show only changed lines.

## 4. Render

Map each card's `engine` to a bundled skill. Invoke the skill (Skill tool) and pass: the input
video, `draft.words.json`, the card's `prompt` verbatim, brand colors/fonts/logo from the profile,
exact timings from the plan, output path in `work_dir`, target size and fps.

| engine | skill | used for |
|---|---|---|
| cut | (done in step 2) / `talking-head-recut` | punch-in zooms on key lines, jump-cut rhythm |
| captions (fast default) | `engines/captions.py` | plain word-timed captions: C1, the built-in default, or "simple captions" |
| captions (designed) | `embedded-captions` | C2-C6 looks, words behind the subject (matting), anything captions.py can't draw |
| overlay | `talking-head-recut` | lower-thirds, callouts, background text on talking head |
| motion | `motion-graphics` | hook titles, end cards, animated text, transitions + transition SFX |
| composite | `general-video` | b-roll cutaways, subject cut-out in front of/behind cards, multi-layer builds |
| (assets) | `media-use` | music/SFX/images only when assets/ has none; keys optional, skip if missing |

**Captions, fast path.** `engines/captions.py` is deterministic and verbatim: 2-3 word groups, each word
popping in on its own timestamp, white heavy text with a dark stroke, one accent word. The font is the owner's
brand font when the profile has one (`brand.fonts.files` not empty), else bundled Inter. Use it when the caption
card is C1 or there is no caption card, and run it on the video that already has the graphics (captions go on top):
```bash
python3 scripts/rr.py run -- python3 engines/captions.py "$W/graphics.mp4" --words "$W/draft.words.json" \
  --out "$W/captioned.mp4" --accent-color "<brand.colors.accent>" --max-words <profile.captions.max_words_per_line, default 3> \
  [--font "<main folder>/<profile.brand.fonts.files[0]>" --font-family "<profile.brand.fonts.heading>"] \
  [--accent <the one emphasis word, as spoken>]
```
Pass `--font`/`--font-family` only when `brand.fonts.files` has an entry (ttf, otf, woff or woff2). If the file is
missing or unsupported it prints one `warning: font not found` line and falls back to Inter: tell the user in one
line. Weight stays 800 (a regular-only file gets synthesized bold); add `--font-weight 400` if the brand font is
already black/heavy. No graphics layer -> pass `$W/draft.mp4`. It keeps the input's audio bit-exact and leaves pure
fillers (um, uh) off the caption track; every other word is shown exactly as spoken. It also writes
`$W/captioned.captions.json` (font_family, font_source brand|bundled-inter|system-fallback, font_path, accent_color,
accent_word, max_words, groups, words); the taste gate reads it, so leave it next to the video. It only does this
one look (no box, no karaoke fill): for any other caption card or behind-subject words, use `embedded-captions`;
for captions that are part of an overlay card layout on a talking head, `talking-head-recut`. Exits 1 with "disk
is almost full" when HyperFrames has under 1 GB: handle as in step 0.

Order: draft -> composite (b-roll) -> overlay/motion (`graphics.mp4`) -> captions on top
(`captioned.mp4`) -> sound (`sound.mp4`) -> final.
Prefer ONE HyperFrames composition with `draft.mp4` as the base layer and each card as a layer
(designed captions from `embedded-captions` go in it too; then name its output `captioned.mp4`);
if chaining separate renders, intermediates at CRF 16 in `work_dir`. captions.py is its own short pass
(one extra encode at CRF 19, fine). The sound step always takes the last video, `captioned.mp4`.
Keep text inside the 9:16 safe zone (same as `styles/README.md`): top 220 px and bottom 320 px clear,
right 140 px clear in the lower half (platform buttons); a card prompt's exact positions win.
Fonts: profile fonts (files in assets/fonts) else defaults; tight tracking on titles, eased motion
(no linear moves), brand palette only.

**Sound** (always; triggers: "make it punchy", "add sound design"). Preset = the S card in the mix, else
the S card in `profile.default_mix`, else S1: S1 `clean`, S2 `punchy`, S3 `cinematic`, S4 `calm`,
S5 `clean` + `--music`. "make it punchy" -> S2 for this edit; a re-edit reruns only this step.
```bash
python3 scripts/rr.py run -- python3 engines/sound.py "$W/captioned.mp4" --out "$W/sound.mp4" \
  --edl "$W/edl.json" --captions "$W/draft.words.json" --preset <preset> [--music "<assets/music/track>"]
```
Voice polish, whooshes on the EDL cuts, hook riser/hit, caption pops (punchy), room-tone bed, ducked
music; re-normalised to -16 LUFS, video stream copied. Multi-clip joins: omit `--edl` (scene detection).
Ran with `--music` -> skip the Music step and copy `sound.mp4` to `final.mp4`.

**Music** (skip if `profile.music.preference` is none, or the sound step already mixed it). Normalize the track to the voice level,
then automate: -18 dB under speech, -8 dB in gaps, 0.25 s ramps, 0.5 s fade in, 1.5 s fade out:
```bash
F=$(python3 scripts/rr.py duck-filter "$W/draft.words.json" --duration <video seconds>)
ffmpeg -v error -y -i "$W/sound.mp4" -stream_loop -1 -i "<assets/music/track>" -filter_complex \
 "[1:a]atrim=0:<video seconds>,asetpts=N/SR/TB,loudnorm=I=-16:TP=-2,aresample=48000,${F}[m];[0:a][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[a]" \
 -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -ar 48000 -movflags +faststart "$W/final.mp4"
```
No music -> copy `sound.mp4` to `final.mp4` (no re-encode).
Transition SFX come only from the sound step (one per cut); it replaces M2's whoosh, never doubles it.

**Deliverables** into `export_dir`: `final.mp4`, `draft.mp4`, `edl.json` (multi-clip: `edl_01.json`,
`edl_02.json`, ...), `plan.md` (approved
version, plus a "Caption corrections" list if any word was fixed), and `caption.txt` only if
`profile.post_caption.draft` is true. caption.txt starts with
`DRAFT - written by AI, read and edit before posting.` and uses the profile tone.

## 5. QA (never say "done" before this)

```bash
python3 scripts/rr.py run -- python3 engines/qa.py "<export_dir>/final.mp4" --frames 6 --out "$W/qa" --expect <WxH>
```
Read `probe.json` and ALL 6 frames. Checklist:
- [ ] QA PASS line; WxH exact; 30 fps; H.264 + AAC; duration within 0.5 s of plan
- [ ] loudness: qa.py fails outside -20..-12 LUFS (target -16); also read `audio.true_peak_dbfs` in
      probe.json, it must be <= -1
- [ ] frame 1 shows the hook (title/card visible inside the first 2 s)
- [ ] captions readable, inside safe zone, never covering the face, spelled as spoken
- [ ] caption text matches `draft.words.json` word for word (spot-check 2 lines)
- [ ] brand colors/fonts used; logo crisp, not stretched
- [ ] no black/frozen frames, no stacked effects, end card present and on-brand
- [ ] music audible in gaps, clearly under speech (if music)

One obvious issue -> fix once, re-run QA. Still failing -> deliver with an honest note.

**Taste gate** (never say "done" before it passes):
```bash
python3 scripts/rr.py run -- python3 engines/taste.py --profile "<main folder>/.reelready/style-profile.json" \
  --plan "<export_dir>/plan.md" --captions "$W/captioned.captions.json" --sound "$W/sound.sound.json" --mix <IDs used>
```
Must end `TASTE PASS`. On `TASTE FAIL`, fix each named rule once: brand-choices / palette-in-plan -> rewrite the
Brand choices bullets; accent-color / brand-font -> re-run captions.py with `--accent-color` / `--font`;
signature -> swap the mix to exactly one house signature card; sound-preset -> re-run sound.py with the S card's
preset. Re-render only the affected layer, then re-run qa.py and taste.py. If the profile genuinely has nothing
to give (no colors, fonts, logo or references), say so to the user in one line and run taste.py with `--profile` only.

**Deliver** in 3 lines:
```
Done: exports/<slug>/final.mp4  (<dur>, <WxH>, <LUFS> LUFS)
Cut <src> -> <new>; styles <IDs>; music <file|none>
Check before posting: <generated copy to approve | caption corrections | nothing>
```
Then clean `work_dir` proxies (keep transcript + words for re-edits).

## 6. Write the post copy (optional)
When the user says "write the post for this" (or "post copy", "hashtags for this"), or automatically
after delivery when `profile.copy.auto` is true: invoke **reelready-copy** on this job. It writes
`<export_dir>/post.md` (3 hooks, caption, CTA, hashtags, all marked DRAFT) from `draft.words.json` +
the profile. Otherwise offer it as the one next step. Never post it.

## Re-edits
"make the captions bigger", "swap the hook", "no music": reuse `work_dir` (transcript, EDL,
draft), redo only the affected render steps, re-run QA, write to the SAME export folder
(final.mp4 replaced, old one kept as final-v1.mp4).
