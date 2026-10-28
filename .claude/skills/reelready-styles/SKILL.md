---
name: reelready-styles
description: ReelReady style catalog. Use when the user says "show me the styles", "what styles do you have", "style guide", "build me a mix", "suggest a mix", "use styles X+Y", or asks what a style code like H1, C3 or X2 means. Opens the local style guide page or lists cards in chat, resolves a mix of card ids into one combined edit instruction, enforces the one-signature-effect rule, and hands the mix to reelready-edit.
---

# ReelReady styles

The catalog lives in `styles/cards/*.json` (one card per file, schema in `styles/README.md`),
sketches in `styles/sketches/`, ready-made mixes in `styles/mixes.json`. The visual page is
`styleguide/index.html`. Run everything from the repo root.

## 1. "Show me the styles" -> open the page

```bash
python3 styleguide/serve.py
```

Run it in the background (it keeps serving until stopped). It rebuilds the page from the cards,
serves it on the port in `reelready.config.json` (`styleguide.port`, default 4810; it tries the next
port if busy) and opens the browser. Tell the user, in one or two lines:

> Your style guide is open at http://localhost:4810. Tap **Add** on the styles you like, then
> **Copy prompt** at the bottom and paste it here.

If the browser didn't open, give them the URL. If Python can't serve, open
`styleguide/index.html` directly (it works as a plain file; only the brand name refresh needs the server).
Stop the server when the user is done or the session ends.

## 2. "What styles do you have?" -> list in chat

When the user would rather not leave the chat, read `styles/cards/*.json` and list them grouped by
category in this order, one line each: `ID  Name  (one-liner)`.

Hook (H) . Captions (C) . Layout (L) . Proof (P) . B-roll (B) . Signature (X) . Motion + pace (M) . Outro (O)

Keep it scannable. Offer the page for pictures, and offer a suggested mix (section 5).
For "what is H1?", answer with the card's `description`, `duration_hint` and `needs` in plain words,
not the raw prompt.

## 3. Resolve a mix

Input: anything like "use styles H1 + C2 + O1", "H1, C2 and O1", a ready-made mix by name ("the Cafe
story mix": its `ids` in `styles/mixes.json`), or a pasted prompt from the page (which already starts
with `Edit the newest clip in raw footage. Use styles: ...`, or `Use style: H1.` for a single card).

1. Parse ids: split on `+`, `,`, `and`, spaces; uppercase; de-duplicate.
2. Load `styles/cards/<ID>.json` for each. Unknown id -> say which one and show the closest ids in
   that category. Never invent a card.
3. Sort into category order (hook, captions, layout, proof, broll, signature, motion, outro).
4. Check conflicts (section 4).
5. Check `needs` against what exists: `matting` (local subject cut-out available), `transcript`
   (always produced by ingest), `assets:logo` / `assets:music` (files in the main folder's `assets/`),
   `broll` (extra clips or photos in raw footage / assets). If something is missing, say what the card
   will do without it (most cards say "skip and tell the user") before rendering, not after.
6. Build ONE instruction, exactly in this shape:

```
Edit the newest clip in raw footage. Use styles: H1 + C1 + O1.

H1 · Chunky title behind head (first 3s)
<H1 prompt, verbatim>

C1 · Bold white + accent word (whole video)
<C1 prompt, verbatim>

O1 · End card (last 4s)
<O1 prompt, verbatim>

Keep captions verbatim. Show me the plan first.
```

7. Invoke the **reelready-edit** skill with that instruction as the request. It reads the IDs from the
   `Use styles:` line, so the instruction above is the whole handoff (it maps each card's `engine` to the right engine skill, fills the
   `{{brand.primary}}`, `{{brand.accent}}`, `{{font.display}}`, `{{font.body}}` tokens from the profile's
   `brand.colors.primary`, `brand.colors.accent`, `brand.fonts.heading`, `brand.fonts.body`, and shows the
   plan before rendering). Use card prompts verbatim; don't rewrite them.

If the user only wants to save the mix as their default, write it with
`python3 scripts/rr.py profile-merge -` and `{"default_mix": ["H1","C1","L1","B1","O1"]}` on stdin.

## 4. The one-signature rule (and other conflicts)

- **One signature effect per idea.** Signature cards are `X1`-`X6`. If the mix has two or more, say
  so in one friendly line and ask: keep one, or use them in different sections? If the user already
  said "just do it", keep the first one in the mix order and mention it in the plan.
  Never put two signature effects on the same moment.
- **One per slot.** Only one hook, one caption style and one outro per video. These pairs, plus
  effects that fight for the same spot (e.g. `H1` with `X3`, `L4` with background-swapping X cards),
  are listed in each card's `avoid_with`. When two cards conflict, suggest which to keep based on
  the user's goal; don't silently drop anything.
- `pairs_with` is a hint for suggestions, not a requirement.

## 5. Suggest a default mix from the profile

Read the profile (`python3 scripts/rr.py where --json` gives its path). If `default_mix` is set, offer
that first. Otherwise pick by business type and goal, then sanity-check `needs` against their assets:

The first five rows are the named mixes in `styles/mixes.json` (Cafe story, What to order, Salon
glow-up, Job walk, Listing tour); the user can just say "use the Job walk mix".

| Situation | Mix |
|---|---|
| Cafe / bakery owner telling a story | H1 + C1 + L1 + B1 + O1 |
| Restaurant "what to order" / new item | H2 + C2 + B4 + M2 + O3 |
| Salon, barber, beauty before/after | H5 + C6 + P2 + M1 + O1 |
| Contractor / trades showing the work | H4 + C4 + L3 + B1 + O3 |
| Realtor listing tour | H6 + C6 + L1 + P4 + X4 + O1 |
| No b-roll at all, just one take | H1 + C1 + L1 + M1 + O1 |
| Calm, premium brand | H6 + C6 + L4 + O1 |
| Wants one "wow" moment | add one X card that fits (X6 spotlight is the safest; X1/X2 need real photos) |

Adjustments:
- No logo in assets -> avoid `H2`; `O1` falls back to the business name.
- No b-roll -> skip `B1`-`B4`, `L2`, `L3`, `H5`, `M3`.
- No reviews provided -> skip `P1`/`P2` (never invent reviews).
- Profile `captions.card` set -> use that caption card.
- Keep suggestions to 4-6 cards. More effects is not better.

Say the mix in one line with a reason per card, e.g.
"H1 (your opening line big behind you) + C1 (your captions, word for word) + L1 (your name) +
B1 (cut to the pastries when you mention them) + O1 (address + 'come say hi')". Then ask "Want me to
edit with this?" and on yes, resolve it (section 3).
