# ReelReady script writer: design

Status: draft for approval, 2026-11-01. Nothing built yet.

## Why

Owners freeze in front of the camera. "What do I even say?" is the step before every clip, and the
kit currently starts after it. A script writer closes that gap so the loop becomes
idea, script, film, edit, post.

The risk is slop: an AI writing words an owner then recites in a voice that isn't theirs, with facts
that aren't true. The whole kit is built against that (verbatim captions, story pass that never
writes a line, generated copy flagged). The script writer has to hold the same line from the other
side: it may write, but only from the owner's own facts and phrasing, and every line is flagged as
written by AI.

## Goals

- From one sentence ("script for the new chai menu", "what should I post this week?"), produce a
  short script the owner can film in one or two takes, in their own voice, in under 2 minutes.
- Every fact in the script traces to the style profile, a past transcript, or something the owner
  told it in this conversation. Missing facts become questions, never guesses.
- The script sounds like the owner: built from their past transcripts when there are any.
- Shape it with the same four story structures the edit's story pass uses, so the filmed clip
  needs few or no moves in the edit.
- Hand off cleanly to the edit: when the owner films it and says "edit this", the edit knows which
  script it was and uses the script's structure and hook as hints.

## Non-goals

- No content strategy, competitor research, format matrices, audience analysis or hook libraries
  learned from performance data. That is the paid implementation layer (docs/business-model.md).
- No posting, scheduling or publishing (hard rule 7).
- No voiceover generation, no AI voice, no teleprompter app.
- Captions never come from the script. Captions stay verbatim from what was actually said on film
  (hard rule 1), even if the owner went off-script.

## Anti-goals (failure even if it "works")

- A script with a price, date, number, award, review, offer or story the owner never gave.
- Copywriter voice: "game-changer", "elevate", rule-of-three lists, rhetorical hype, em dashes,
  exclamation marks. A script the owner would be embarrassed to say out loud.
- Long scripts. Anything an owner can't say in one breathless-free take of about 45 seconds.
- Scripts that read identical across businesses (same opener, same CTA shape).
- Generated lines presented as the owner's words anywhere.

## The skill: `reelready-script`

New folder `.claude/skills/reelready-script/` with `SKILL.md` and `references/` (formats, voice,
examples). Same shape as `reelready-copy`.

Triggers: "write me a script", "what should I say", "script for <topic>", "give me reel ideas",
"what should I post this week", "help me plan a video".

### Two modes

1. **Ideas** ("what should I post?"): 3 idea cards. Each card names its source (a profile fact,
   a line from a past reel, something the owner said today), a structure, a one-line hook in the
   owner's words where possible, and what to film. Owner picks one, then mode 2 runs.
2. **Script** (a topic is given or picked): one script in `script.md`.

### Inputs, in order of trust

1. What the owner says in this conversation (the topic, plus answers to at most 3 short questions).
2. Style profile: `business.*`, `tone`, `platforms`, `copy.cta`, `reference_style.hook_patterns`,
   `reference_style.pacing`, `aspect`.
3. Voice: up to 5 most recent `transcript.json` files under `<main folder>/.reelready/work/*/`.
   Used for phrasing, sentence length and recurring phrases, never as a source of new facts unless
   the line states one ("we open at seven" is a usable fact).
4. Nothing else. No web search for facts.

### The fact interview

Before writing, list the facts the script needs (what, a number, when, where, why it matters).
Anything not in inputs 1 to 3 becomes a question. Ask at most 3, one message, plain words
("What time do the croissants come out?"). If the owner skips one, the script either leaves that
beat out or marks it `[ASK: ...]` inline. Never fill it in.

### What a script looks like

Default format is **talking points**: 3 to 6 beats, each one short line in the owner's voice, said
in their own words on camera. Talking points keep the delivery natural and keep the owner's real
phrasing in the final captions. Optional **word for word** format when the owner asks
("write it out exactly"): same beats, full sentences.

```
DRAFT - written by AI. Change anything that doesn't sound like you.

# Script: almond croissant Saturdays
Corner Bean Coffee · structure: hook, context, payoff · about 25 s · 9:16

Hook (first 2 s, to camera)        [GENERATED - approve?]
  "Saturdays at eight, these come out."     from your words: "the almond croissants come out at eight"

Beats                              [GENERATED - approve?]
  1. Show the tray. Say what they are.
  2. "Most people don't know the back room is a roaster."   your line, reel 2026-10-28
  3. Invite: "Visit us Saturday morning."                   copy.cta

Film this
  A-roll  you at the counter, phone at eye level, window light on your face
  B-roll  tray coming out (3 s), close-up of one croissant (2 s), the roaster door (2 s)

Facts used                        source
  croissants out Saturdays at 8   your past reel, 2026-10-28
  roaster in the back room        your past reel, 2026-10-28
  Visit us                        profile copy.cta

Not used (you didn't tell me)
  price, how many you bake

Say "go" to save it, or tell me what to change.
```

Rules for the content:

- Length from `script.seconds` when set, else 30 s. Budget about 2.5 spoken words
  per second (30 s is about 75 words).
- Structure: one of the four in `reelready-edit/references/story.md`, named in the header. Hook
  first, never a greeting.
- Hook: the six angles in `reelready-copy/references/hooks.md`, under 8 words, built from a fact or
  line the owner gave. Shared rules, shared banned list.
- Every quoted line that came from a past transcript says so ("your line, reel <job>").
- One CTA, from `copy.cta` if set.
- Shot list: A-roll and 2 to 4 B-roll shots the owner can film in 5 minutes with a phone. Plain
  instructions (light, distance, how long).
- Same style bans as post copy: no em dashes, no semicolons, no exclamation marks, no rule of three,
  no emojis unless tone asks, banned words list from `reelready-copy/references/captions.md`.

### Where it saves

`exports/<YYYY-MM-DD>-<slug>/script.md`, via `python3 scripts/rr.py export-dir "<slug>"`. The same
folder later gets the edited reel, so script and video live together. Saved only after "go".
Overwrite needs a yes; otherwise `script-v2.md`.

### Deterministic check: `engines/script_check.py`

Stdlib only, like `taste.py`. Run before showing the script; fix and re-run once on FAIL.

```
script_check.py --script script.md --profile style-profile.json [--work-dir <main>/.reelready/work] [--seconds 30]
```

Rules, each printed `SCRIPT ok|FAIL <rule>: <reason>`, then `SCRIPT PASS` or `SCRIPT FAIL` (exit 1):

- `draft-banner`: first line is the DRAFT banner.
- `flagged`: Hook and Beats sections carry `[GENERATED - approve?]`.
- `length`: spoken words (quoted lines + beat lines) within the budget for `--seconds` (default from
  profile pacing or 40) at 2.5 words/s, plus 15 percent.
- `hook-length`: hook under 8 words.
- `banned`: none of the banned words or patterns (em dash, semicolon, exclamation mark, list from
  the copy skill's reference, kept in one shared file the engine reads).
- `facts-table`: a "Facts used" table exists and every row has a source.
- `numbers-sourced`: every number in Hook and Beats, digits or number words ("eight", "forty",
  "half"), also appears in a Facts row or is marked `[ASK: ...]`. This is the mechanical guard
  against invented prices and dates.
- `sources-real`: each Facts row's source is checked against the real input, not just the table.
  `profile <field>`: the field exists and its value contains the fact's key words.
  `your past reel <job>`: `<work-dir>/<job>/transcript.json` exists and contains the quoted words
  (case and punctuation ignored). `you told me today`: allowed, counted, and listed in the output so
  the owner sees which facts rest only on this chat. Anything else fails.
- `structure`: header names one of the four structures.

The fact trace beyond numbers stays a checklist item in the skill (it needs judgment).

### Hand-off to the edit

Small addition to `reelready-edit` step 0/2: if the newest export folder (or one from the last 14
days) has a `script.md` and no `final.mp4`, ask once: "Is this the clip for your script
'<title>'?" On yes:

- Write the edit into that folder.
- Use the script's structure as the story pass default and its hook line to find the hook sentence
  in the transcript (closest match, still the owner's spoken words).
- The plan shows "Script: <title>, followed / changed" in one line.
- Captions remain verbatim from the transcript. If the owner went off-script, the reel shows what
  they said.

### Profile

No new required fields. Optional `script: {"format": "talking-points"|"word-for-word", "seconds": 30}`
merged via `rr.py profile-merge`. Example profile and profile/README.md document it.

## Files touched

New: `.claude/skills/reelready-script/SKILL.md`, `references/formats.md`, `references/voice.md`,
`references/examples.md` (two worked examples, generic businesses), `engines/script_check.py`,
shared banned list file (moved out of `reelready-copy/references/captions.md` into a file both the
copy skill and the engine read, or the engine parses the existing file), tests fixtures
(`tests/smoke/fixtures/script_good.md`, `script_invented_price.md`, `script_long.md`).

Changed: `CLAUDE.md` (intent table row, pipeline step 0 "Script (optional)"), `reelready-edit/SKILL.md`
(hand-off paragraph), `engines/README.md` (ninth contract), `tests/smoke/run.sh` (script check
good must PASS, bad must FAIL), `profile/example-profile.json` + `profile/README.md`,
`docs/architecture.md`, `README.md` (one line in what it does), `tasks/todo.md`.

## Decided

- It ships in the free kit (kit author decision, 2026-11-01).
- Every generated line is flagged `[GENERATED - approve?]` and the file starts with the DRAFT banner.

## Builder's calls (marked, change if wrong)

- Default format talking points, word-for-word on request.
- At most 3 fact questions per script.
- Voice from the last 5 transcripts, no separate voice engine in v1.
- Ideas mode lives in the same skill, not a separate one.
- Script length default 20 to 40 s.
- Numbers check is mechanical; other fact checks are a skill checklist.

## Settled after the builder check (builder's calls unless noted)

These override anything above that reads differently.

1. **Fact check uses real sources.** `script_check.py` takes `--work-dir` and runs `sources-real`
   (above). Number words count as numbers. The skill always writes source labels in one of the
   three fixed forms so the engine can check them.
2. **Length.** `script.seconds` from the profile, else 30. Budget 2.5 words/s, so 30 s is about
   75 spoken words, and the check allows plus 15 percent. `reference_style.pacing` is free text
   about cut rhythm and is not used for length.
3. **script.md grammar** (the engine parses exactly this):
   - Line 1: the DRAFT banner.
   - `# Script: <title>`, then one meta line containing `structure: <one of the four>` and
     `format: talking-points` or `format: word-for-word`.
   - `## Hook  [GENERATED - approve?]`, `## Beats  [GENERATED - approve?]`, `## Film this`,
     `## Facts used`, `## Not used`. Facts rows are `- <fact> | <source>`. Beats are numbered lines.
   - Spoken words: in talking-points, only text inside double quotes in Hook and Beats; stage
     directions are not spoken. In word-for-word, every Hook and Beats line is spoken.
   - `banned` and `numbers-sourced` scan Hook and Beats only. Film this is plain instructions.
4. **Draft location.** The draft lives at `<main>/.reelready/work/script-<slug>/script.md` and is
   checked there. `rr.py export-dir` runs only on "go", then the file is copied in. Abandoned drafts
   leave nothing in exports. A second version in the same export folder is `script-v2.md`.
5. **Ideas mode with no sources.** If the profile is thin and there are no transcripts, ask the 3
   fact questions first, then write cards. Cards appear in chat only: not saved, not run through
   the check, but every card line carries `[GENERATED - approve?]` and its source.
6. **Hand-off.** List up to 3 unfilmed scripts from the last 14 days, newest first, and ask which
   one this clip is for, with "none" as an option. Reuse that folder (its work dir already exists
   from export-dir). The folder date stays the script date; plan.md notes the filming date.
7. **Banned list moves** to one plain file, `engines/banned.txt` (one word or pattern per line,
   `re:` prefix for regex). `reelready-copy/references/captions.md` points to it instead of listing
   words inline. Both skills and the engine read the same file.
8. **Today's facts are checked too** (added after the dry runs). The skill appends each owner
   message about the script, verbatim, to `<work>/script-<slug>/owner.txt`. `script_check.py
   --chat owner.txt` fails any `you told me today` quote not found in that file. A price in the
   script must match a sourced price ("3 days" does not source "a $3 fee").
