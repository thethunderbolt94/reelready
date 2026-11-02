---
name: reelready-script
description: ReelReady script writer. Before filming, drafts what the owner says on camera - a hook, 3 to 6 beats, a shot list and a facts table with sources - built only from the style profile, the owner's past reel transcripts and what they say in the chat, every line marked [GENERATED - approve?], checked by engines/script_check.py, saved to exports/<date>-<slug>/script.md on "go". Also gives 3 idea cards when asked what to post. Use when the user says "write me a script", "what should I say", "script for <topic>", "give me reel ideas", "what should I post this week", "help me plan a video". Never posts anything.
---

# ReelReady script

Run from the repo root. CLAUDE.md hard rules apply: every word here is generated copy (rule 2),
nothing is posted or sent (rule 7), write only to `exports/` and `.reelready/`.

The line this skill holds: **it may write, but only from the owner's own facts and phrasing.** A
script with a price, date, number, story or claim the owner never gave is a failed script, even if
it reads well. When a fact is missing, ask. Never fill it in.

## 0. Preflight (silent when fine)

```bash
python3 scripts/rr.py where --json
```
- `configured` false or `profile_exists` false -> invoke **reelready-setup** first, then come back.
- Read the profile: `business.*`, `tone`, `platforms`, `aspect`, `copy.cta`, `script.format`,
  `script.seconds`, `reference_style.hook_patterns`. Any field missing -> skip it silently and use
  the default named in this file (`aspect` default 9:16, `tone` default warm, direct, local).
- Voice: the 5 newest `transcript.json` (or `draft.words.json`) under `<work>/*/` by file
  modification time, skipping `script-*` folders. Read their text. Note the owner's recurring
  phrases, how long their sentences are, words they use for their own product. Details:
  `references/voice.md`.
- No transcripts yet -> say once, as the first line of your first message: "I don't have any of your
  past videos yet, so what I write won't sound fully like you yet. Change any line that doesn't."

## 1. Pick the mode

- The owner named a topic ("script for the new chai menu") -> **Script** (step 3).
- The owner asked what to post, or gave no topic -> **Ideas** (step 2).

## 2. Ideas mode

Write 3 idea cards in chat. Each idea comes from a real source: a profile fact, a line from a past
reel (name the reel folder), or something the owner told you today. Different angles across the 3
(a product, a behind-the-scenes moment, a customer question or a change in the business).

```
1. <working title>                                  [GENERATED - approve?]
   Source     your past reel 2026-10-28-tuesday-roast: "the back room is a roaster"
   Structure  hook, context, payoff · about 25 s
   Hook       "Most people don't know the back room is a roaster."
   Film       you by the roaster door, then the beans pouring
```
The Source line uses the same three forms as the Facts table in step 4 (`profile <field>`,
`your past reel <folder>: "<quote>"`, `you told me today: "<their words>"`).

- Thin profile and no transcripts -> there is nothing to cite. Ask these 3 first, in one message:
  "What's new this week?", "What do customers ask you most?", "What's one thing people don't know
  about this place?" Then write the cards from the answers.
- Cards stay in chat: not saved, not run through the check. Ask: "Which one, 1, 2 or 3?" Then run
  step 3 on that idea.

## 3. Fact interview

List the facts the script needs: what it is, one concrete detail (a number, a time, a name), when
or where, and the invite. "Why it matters to a customer" is optional: use it if the owner gave it,
never ask for it unless it is the point of the reel. For each fact, look in this order: what the
owner said today, a past transcript line, the profile. Anything not found becomes a question.

- At most 3 questions per round, in one message, plain words: "What time do the croissants come
  out?" At most 2 rounds in a whole conversation, so after ideas mode asked its 3, ask only what is
  still missing for the picked idea (often nothing).
- Sources disagree -> today's chat wins over a past reel, a past reel over the profile. If they
  really clash (different days, different prices), ask instead of choosing.
- Keep the owner's hedges ("usually", "about", "most days"). Never turn "usually 3 days" into
  "3 days".
- No `copy.cta` -> make the invite one of the questions ("How should people get in touch: visit,
  call or message?"). If there's no answer, use the plain shape for their business from the CTA
  table in `reelready-copy/references/captions.md`, with no detail they didn't give.
- The owner skips one -> leave that beat out, or keep it with `[ASK: <the question>]` inline so
  they can fill it while filming. Never guess.
- Never use the web for facts.

## 4. Write the draft

Exact shape and both formats: `references/formats.md`. Worked examples: `references/examples.md`.

- **Format**: `profile.script.format`, else talking points. Word for word only when asked
  ("write it out exactly", "give me the exact words").
- **Length**: `profile.script.seconds`, else 30 s. About 2.5 spoken words a second, so 30 s is
  about 75 words. Shorter is fine. The meta line's "about <n> s" is your estimate of this script:
  spoken words / 2.5, counting about 8 words for each beat that is a direction, rounded up to the
  next multiple of 5 s.
- **Structure**: one of the four from `reelready-edit/references/story.md` (hook, context, payoff ·
  list · before, after · question, answer), named in the meta line. Hook first, never a greeting.
- **Hook**: under 8 words, built from a fact or a line the owner gave. Use the angles and the
  "Never" list in `reelready-copy/references/hooks.md`; `reference_style.hook_patterns` breaks ties.
- **Beats**: 3 to 6. Prefer the owner's own past line, quoted, over a line you wrote. In talking
  points a beat can be a direction ("Show the tray. Say what they are.") when the owner will say it
  better in their own words. A direction is held to the same fact rule as a quote: "Say it's free"
  needs a row saying it's free. Write numbers the way the owner said them.
- **One invite** at the end, from `copy.cta` if set, shaped to this script.
- **Film this**: A-roll (where they stand, phone at eye level, light) and 2 to 4 B-roll shots they
  can film in 5 minutes, each with a length in seconds. Places and things only, no claims.
- **Facts used**: every fact in Hook and Beats, one row each, source in one of exactly three forms:
  `profile <dotted.field>` · `your past reel <folder>: "<exact quote>"` ·
  `you told me today: "<what they said>"`. One fact per row. Quote the shortest exact words that
  hold the fact. Any number in Hook or Beats (digits or words) must appear in a row, and a price
  must appear as a price.
- **Today's facts come from the owner's notes file.** As soon as the owner tells you anything for
  this script (the topic, answers to questions), append their message, verbatim and unedited, as
  one line to `<work>/script-<slug>/owner.txt`. A `you told me today` quote must be copied exactly
  from that file. The check reads it with `--chat` and fails any today-quote that isn't there.
- **Not used**: what a viewer might expect that the owner didn't give (price, hours), so the
  owner sees the gap.
- Style: `profile.tone` (default warm, direct, local). Words from `engines/banned.txt` never. No
  rule-of-three lists, no closing moral, no emojis unless the tone asks. Nothing the owner would be
  embarrassed to say out loud.

Save the draft to the work folder, not exports:

```bash
mkdir -p "<work>/script-<slug>"     # <work> from where --json
```
Write `<work>/script-<slug>/script.md`.

## 5. Check (never show a script that fails)

```bash
python3 scripts/rr.py run -- python3 engines/script_check.py \
  --script "<work>/script-<slug>/script.md" --profile "<profile>" --work-dir "<work>" \
  --chat "<work>/script-<slug>/owner.txt"
```
- `SCRIPT PASS` -> show it.
- `SCRIPT FAIL` -> fix the named rule once and re-run. `numbers-sourced` -> source the number or
  turn it into `[ASK: ...]`. `sources-real` -> fix the quote to the exact transcript words or drop
  the line. `length` -> cut a beat. Still failing -> show it with one line on what's wrong.
Then the checks the engine can't do, by eye: every claim in Hook and Beats (quotes and directions)
traces to a row; no rule-of-three list, no closing moral, no chain of 3+ fragments; hedges kept;
every line sounds like something they'd say out loud.

## 6. Show, then save on "go"

Show the script in chat exactly as written. Under it, if the check printed a `today-only facts`
note: "These come only from what you told me today, please make sure they're right:" then the facts
(one line if 1 or 2, a short list if more). Then: "Say 'go' to save it, or tell me what to change." Changes -> edit the draft, re-run
step 5, show again.

On "go", for a new script:
```bash
python3 scripts/rr.py export-dir "<slug>"
```
Copy the draft to `<export_dir>/script.md`, then move the draft and the notes out of scratch so
`work/` only holds job folders: `mv "<work>/script-<slug>/script.md" "<work>/script-<slug>/owner.txt" "<work_dir>/"`
and `rmdir "<work>/script-<slug>"` (the folder is empty by then; never delete anything else).

Re-doing a script that already has an export folder: do not call `export-dir`. Save
`script-v2.md` in that folder (overwrite `script.md` only with a yes).

Finish with two short lines: where it's saved, and "Film it, drop the clip in raw footage and say
'edit this'. I'll match it to this script." Nothing is posted or sent anywhere.

## Captions stay theirs

The script is a guide for filming, not the caption track. When the clip is edited, captions come
verbatim from what the owner actually said on camera (hard rule 1), even where they went off-script.
That is a feature: their own words beat ours.
