# Script by interview (the default)

The owner said she would never say our script like that. So we stop writing lines. We ask, she
answers, and the script is her answers, picked and put in order. Same line the edit holds
(`reelready-edit/references/story.md`): reorder and select, never write.

## 1. Ask

Topic named, or an idea card picked. Then 5 to 8 short, open, concrete questions, ONE OR TWO PER
MESSAGE, plain words, and wait for each answer. Pick from this menu, in roughly this order, and
tailor the wording to the topic:

| Id | Ask |
|---|---|
| what | "What is it? Say it like you would to a friend." |
| who | "Who is it for?" |
| moment | "Tell me about a time it really happened. What did you see?" |
| they say | "What do people say about it?" |
| detail | "What's one detail only you would know?" |
| why | "Why does it matter to you?" |
| invite | "How do people find you, or what do you want them to do?" |

Never ask a question that has a number, price or date as the only answer unless the topic needs it.
Never suggest an answer, never rephrase theirs back as a question ("so it's the best in town?").
The questions are open: "what happened?", not "was it busy?".

## 2. Save every answer verbatim

First, `mkdir -p "<work>/script-<slug>"` (or `script-draft` until there is a topic, then rename).
Keep appending their messages to `owner.txt` as before. Also keep
`<work>/script-<slug>/answers.json`, rewritten after each answer (Write tool, whole file):

```json
[{"id": "A1", "question": "What is it?", "answer": "<their words, untouched>", "ts": "<iso time>"}]
```

- Ids A1, A2, ... in the order asked. Never edit, tidy or merge an answer.
- A typed answer is stored as typed. A voice-note answer is transcribed with
  `python3 scripts/rr.py run -- python3 engines/transcribe.py <note> --out <work>/script-<slug>/note-A3.json`,
  its text stored as the answer, and `"source": "<file name>"` added to that entry.

## 3. Is there enough?

Enough = a moment or detail for the hook, 2 to 4 more lines for the middle, and an invite. If
something is missing, ask ONE follow-up question. Never write the missing line. If the owner says
"that's all", build with what there is and say what is thin.

## 4. Build from the answers only

1. Cut the answers into candidate spans: a sentence, or a clause boundary inside one. A span is a
   contiguous run of ONE answer. You may trim it. You may not add, swap, reorder or join words.
   Case and punctuation can be normalised.
2. Choose one of the four structures (`reelready-edit/references/story.md`): hook, context, payoff ·
   list · before, after · question, answer. Name it in the meta line.
3. The hook is the strongest short span, under about 10 words: a concrete moment or a surprising
   detail. Never a greeting or the "what is it" answer unless it is the surprise.
4. Order the rest by the structure. Skip a span that repeats another. End with the invite.
5. Fit 20 to 40 s: about 2.5 spoken words a second, so 50 to 100 words.
6. A sentence that leans on the one before ("that's why...", "so...") travels with it. If trimming
   would change the meaning, take the whole sentence.
7. Every spoken line cites its answer: `"we put the notes up the same day" (A3)`. In word-for-word
   format the line is the span plus ` (A3)`.
8. Stage directions (shot list, "show the board") are allowed as text with no quote marks, or
   `[in square brackets]` in word-for-word. They are ours, so keep them short and factual.

## 5. The file

Exact shape: `formats.md`, "Interview scripts". Meta line says `source: answers`. Headings carry no
`[GENERATED - approve?]`, because the words are hers. The banner stays, with one extra line saying
the order and the picks are Claude's. Save `answers.json` beside `script.md` (the check reads it).

## 6. Voice-memo path

The owner would rather ramble. Ask for a 1 to 3 minute voice note about the topic ("talk like
you're telling a friend, no script"). Transcribe it, then split it into sentence answers:

```bash
python3 scripts/rr.py run -- python3 engines/transcribe.py "<memo>" --out "<work>/script-<slug>/memo.json"
python3 engines/memo_answers.py --transcript "<work>/script-<slug>/memo.json" \
  --out "<work>/script-<slug>/answers.json" --source "<memo file name>"
```
Ids are M1, M2, ... with start times. Build exactly as above, citing `(M4)`. `engines/story.py`
can order the sentences if the memo is already an EDL-style transcript; the same rules hold. A
memo with too little (under about 40 words of usable content) -> switch to the interview.

## 7. Check, show, save

Same as the main skill: run `engines/script_check.py` (it picks up `source: answers` and runs
`answers-only`), fix the named line once, then show. Under it, one line: "These are all your own
words. I picked and ordered them, so say if the order feels off." A banned-word note from the check
is shown plainly, because it is her word, not ours.

## "Just write it for me"

Only when the owner asks in words like that. Then use the old generated mode (SKILL.md steps 3 to
6): every line `[GENERATED - approve?]`, header `source: generated`.
