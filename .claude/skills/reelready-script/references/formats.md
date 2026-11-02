# script.md: the exact shape

`engines/script_check.py` parses this shape. Keep headings and the meta line exactly as shown.

```
DRAFT - written by AI. Change anything that doesn't sound like you.

# Script: <short title>
<Business name> · structure: <hook, context, payoff | list | before, after | question, answer> · format: <talking-points | word-for-word> · about <n> s · <aspect>

## Hook  [GENERATED - approve?]
"<the first thing said, under 8 words>"

## Beats  [GENERATED - approve?]
1. <beat>
2. <beat>
3. <beat>

## Film this
- A-roll: <where to stand, phone at eye level, light>
- B-roll: <shot> (<n> s), <shot> (<n> s)

## Facts used
- <fact> | profile <dotted.field>
- <fact> | your past reel <export folder name>: "<exact words from that transcript>"
- <fact> | you told me today: "<what they said>"

## Not used
- <what a viewer might expect that the owner didn't give> (you didn't tell me)
```

## What counts as spoken

- **Talking points** (default): only text inside double quotes in Hook and Beats is spoken word
  for word. A beat without quotes is a direction ("Show the tray. Say what they are."); the check
  counts it as about 8 words the owner will say in their own way.
- **Word for word**: every line in Hook and Beats is spoken. No quotes needed.

## Rules the check enforces

| Rule | Means |
|---|---|
| draft-banner | first line starts `DRAFT - written by AI` |
| flagged | Hook and Beats headings carry `[GENERATED - approve?]` |
| structure | meta line names one of the four structures and one format |
| length | spoken words within `seconds x 2.5`, plus 15 percent |
| hook-length | hook 1 to 7 words |
| banned | nothing from `engines/banned.txt` in Hook or Beats |
| facts-table | at least one row `- <fact> \| <source>` |
| numbers-sourced | every number in Hook and Beats, digits or words, is in a Facts row or inside `[ASK: ...]`; a price ($4, four dollars) must match a sourced price |
| sources-real | profile field exists and matches; past-reel quote is really in that transcript; today's quote is really in the owner's notes file (`--chat`), and is listed back to the owner |

`[ASK: <question>]` marks a gap the owner fills while filming. Numbers inside it are not checked.
The words "one", "once", "first" and "second" are not treated as numbers.

## Talking points or word for word

Talking points are the default because owners sound like themselves when they say a point in their
own words, and the reel's captions then carry their real phrasing. Word for word is for owners who
asked for it, or who freeze without exact lines. Keep word-for-word sentences short (under 12 words)
and in the owner's rhythm from `voice.md`.
