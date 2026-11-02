---
name: reelready-copy
description: ReelReady post copy. After an edit, writes the words that go WITH the reel into exports/<job>/post.md - 3 hook options, a short post caption, one CTA line and 5-8 hashtags - all from what the owner actually said plus the style profile, all marked DRAFT for approval. Use when the user says "write the post for this", "write the caption", "post copy", "hashtags for this", "what do I write with this reel", or automatically at the end of reelready-edit when profile.copy.auto is true. Never posts anything.
---

# ReelReady copy

Run from the repo root. Hard rules in CLAUDE.md apply: every word here is generated copy (rule 2),
and nothing is ever posted or sent (rule 7). Write only to the job's export folder.

## 0. Find the job (silent when obvious)

```bash
python3 scripts/rr.py where --json
```
- The job is the export folder just made this session; otherwise the newest folder in `exports/`.
  Say which one in one line.
- Words: `<main folder>/.reelready/work/<same folder name>/draft.words.json` (what survived the cut,
  so what is actually in the reel). Fallback `transcript.json` in the same work folder.
- No words at all (an older export) -> transcribe the export's `final.mp4` into that work folder:
  `python3 scripts/rr.py run -- python3 engines/transcribe.py "<export>/final.mp4" --out "<work>/transcript.json"`.
- Read the profile: `business.name`, `business.handle`, `business.what_we_do`, `business.location`,
  `tone`, `platforms`, `reference_style.hook_patterns`, `post_caption.hashtags`, `copy.cta`,
  `copy.hashtags_extra`. Also read the edit's `plan.md` so hooks don't repeat the on-screen title.

## 1. Source of truth

The words in the reel + the profile. Nothing else.
- Never invent facts, prices, hours, dates, offers, discounts, awards or reviews. If the owner didn't
  say it and the profile doesn't hold it, it isn't in the copy. Thin transcript -> thin copy, that's fine.
- Quote the owner's own phrases where you can. Their words beat yours.
- Tone = `profile.tone`. Missing -> `warm, direct, local`.

## 2. Write

1. **3 hook options** for the on-screen hook title or the first line of the caption. Under 8 words
   each, 3 different angles, each built from a line the owner said. Formulas: `references/hooks.md`.
2. **1 post caption**: 2 to 4 short lines in the owner's voice. Structure: `references/captions.md`.
3. **1 CTA line**: `copy.cta` if set, shaped to this reel; else pick by business (visit, DM, book,
   link in bio). One action only.
4. **Hashtags**: 5 to 8. 2 local (from `business.location`), 3 to 4 niche, 1 to 2 broad, plus
   `copy.hashtags_extra` (counted in the 8). `post_caption.hashtags` false -> write "Off in your
   profile." instead. No location in the profile -> ask once for their town or area (offer to save it).

## 3. Check before writing the file

- [ ] Every claim traces to a line in the words file or a profile field. Name the line if unsure.
- [ ] Hooks under 8 words; curiosity or specificity, never clickbait or ragebait.
- [ ] Caption + CTA read aloud by the owner in 10 seconds (about 25 words max together).
- [ ] No "game-changer", "unlock", "elevate", "dive in" (full list in `engines/banned.txt`).
- [ ] No em dashes, no semicolons, no exclamation marks, no rule-of-three filler ("fresh, local and delicious").
- [ ] No emojis unless a profile tone word asks for them.
- [ ] Plain words a customer would use. Nothing the owner would be embarrassed to say out loud.

## 4. Write post.md and show it

Write `<export_dir>/post.md` in exactly the shape of the example below (overwrite only with a yes if
one exists; else save `post-v2.md`). Show it in chat, then ask one question: "Which hook do you want,
1, 2 or 3?" If they pick a hook that differs from the reel's on-screen title, offer once:
"Want me to swap the hook in the video too?" (reelready-edit, re-edit section).

Never post, schedule or send it anywhere. The owner copies it into the app.

## Worked example

Profile: Corner Bean Coffee, @cornerbean, Anytown, tone warm / unhurried / local, `copy.cta` "Visit us".
Words in the reel: "We roast our beans right here, every Tuesday morning. Most people don't know the
back room is a roaster. And on Saturdays the almond croissants come out at eight."

```
# Post copy: 2026-10-28-tuesday-roast
Corner Bean Coffee · @cornerbean · from draft.words.json + style-profile.json

## Hook options · DRAFT: approve before posting
1. Our back room is a roaster
   (specific · "the back room is a roaster")
2. What happens here every Tuesday morning
   (curiosity · "we roast our beans right here, every Tuesday morning")
3. Almond croissants, out at eight
   (detail · "the almond croissants come out at eight")

## Post caption · DRAFT: approve before posting
We roast our beans right here, every Tuesday.
The back room is our roaster.
Almond croissants come out Saturdays at eight.

## CTA · DRAFT: approve before posting
Visit us on Saturday morning.

## Hashtags · DRAFT: approve before posting
#anytown #anytowncafe #coffeeroaster #houseroasted #freshroastedcoffee #almondcroissant #coffee #smallbusiness

Nothing here is posted automatically.
```

Not allowed in this example: "best coffee in Anytown" (not said), "open from 8" (hours not said, only
croissant time), "free croissant with every bag" (offer not said), "Fresh, local, delicious." (filler).
