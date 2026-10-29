# Story pass (optional, after the cut, before render)

The owner shot the clip in the order they thought of things. That is rarely the order that
holds a stranger for 20 seconds. The story pass fixes the ORDER and the SELECTION of what
they said. It never writes a line, never adds a voiceover, never summarises. If the words
are not in the transcript, they do not go in the reel. This is the line between an edit and slop.

## When to run it
- Always on talking-to-camera clips longer than ~12 s.
- Skip when the clip is a single take under ~10 s, a walk-through with no narration, or the
  owner said "keep it as I said it".

## How
1. `python3 engines/story.py --edl edl.json --transcript transcript.json --list`
   prints the numbered sentences.
2. Pick ONE structure below. Pick the hook sentence: the most specific, concrete line
   (a number, a name, a surprise, a claim), almost never the greeting or "hi I'm...".
3. `python3 engines/story.py --edl edl.json --transcript transcript.json --order 3,0,1,2 --drop 4 --out edl.story.json`
   then render from `edl.story.json` instead of `edl.json`.
4. In the plan you show the owner, print the new order as the sentence text, and say which
   sentences were dropped and why (repeat, aside, weak).

## Structures (choose one, name it in the plan)
- **Hook, context, payoff** (default): strongest line, then the one or two sentences that explain
  it, then the line that lands it (offer, address, invite).
- **List**: "three things" clips. Hook is the sentence that names the count or the best item;
  then items in the owner's order; cut any item that is a repeat.
- **Before, after**: the result first (after), then how it was (before), then how it changed.
  Works for salons, trades, renovations.
- **Question, answer**: the owner asks or implies a question; put it first, answer next, CTA last.

## Hard rules
- Reorder across sentence boundaries only. Never cut inside a sentence to make it shorter.
- A sentence that leans on the previous one ("that's why...", "so...", "the second one...")
  travels with its parent. If you cannot keep them together, keep the original order.
- Drop a sentence only for: exact repeat, false start, aside that mentions nothing from the
  profile, or trailing "anyway..." filler. Never drop the CTA or the address.
- The greeting ("hi, I'm X from Y") moves to second or third place, or is dropped if the
  caption card already shows the name. It never opens the reel.
- Max 2 moves on a clip under 30 s. If the story needs more than that, the fix is a reshoot
  note in the QA report, not a heavier edit.
- One structure per reel. Do not mix.
- The sound card's hook riser (S2/S3) ends on the first sentence's last word, so a long hook
  sentence means a longer riser; prefer a hook sentence under 4 s.
