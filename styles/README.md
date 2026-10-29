# Styles

The style catalog for ReelReady. Each **style card** is one editing recipe: a hook, a caption look,
a layout, a bit of proof, a b-roll move, a signature effect, a pacing rule, an outro or a sound pass. You pick a few
cards, they become one prompt, and Claude renders them onto your clip.

41 cards: Hook 6, Captions 6, Layout 4, Proof 4, B-roll 4, Signature 6, Motion + pace 3, Outro 3, Sound 5.

Browse them visually with the style guide page:

```bash
python3 styleguide/serve.py        # opens http://localhost:4810
```

Or just tell Claude: **"show me the styles"**.

## How cards work

1. You (or Claude, from your profile) choose a **mix** of card ids, e.g. `H1 + C1 + L1 + B1 + O1`.
2. Each card's `prompt` is a concrete, self-contained instruction: where things sit on a 1080x1920
   frame, sizes, timing, easing, which brand tokens to use, and what NOT to do.
3. The mix is stitched into one instruction:
   `Edit the newest clip in raw footage. Use styles: H1 + C1 + ... <each card's prompt> Keep captions verbatim. Show me the plan first.`
4. The editor resolves the tokens from `<main folder>/.reelready/style-profile.json`, shows an edit plan, waits for "go",
   then renders.

### Brand tokens

Prompts never hard-code colors or fonts. They use tokens that the editor fills from the profile:

| Token | Meaning | Profile key |
|---|---|---|
| `{{brand.primary}}` | Main brand color (backgrounds, blocks, bars) | `brand.colors.primary` |
| `{{brand.accent}}` | The one highlight color (emphasis word, pins, arrows, CTA) | `brand.colors.accent` |
| `{{font.display}}` | Display / headline font (serif or chunky) | `brand.fonts.heading` |
| `{{font.body}}` | Caption and UI font (clean sans) | `brand.fonts.body` |

If a value is missing, use the kit's designed defaults rather than guessing a brand color.

### House rules every card follows

- **Captions are verbatim.** Spoken words are never paraphrased. Anything Claude writes itself
  (titles, hooks, labels, CTAs) is flagged in the plan for approval.
- **Safe zone.** No text in the top 220px or the bottom 320px of a 1080x1920 frame, and keep the right
  140px clear in the lower half (platform buttons live there).
- **Readable type.** Nothing meant to be read is smaller than 64px at 1080 wide.
- **Motion.** Ease-out 300ms in, 200ms out unless the card says otherwise.
- **Real proof only.** Reviews, prices, stats and addresses come from the user or the profile. Never invented.

## The one-signature-effect rule

Signature cards (`X1`-`X6`) are the show-stoppers: orbit, wall collage, headline behind you, frame break,
UI world, spotlight. **One signature effect per idea, never stacked.** If a mix has two, they go in
different sections of the video. The style guide page warns you when you add a second one, and the
combined prompt tells Claude to keep them apart.

Sound cards (`S1`-`S5`) do not count against this rule: they shape the audio under the whole video, not
one moment. But only **one S card per edit** (they all `avoid_with` each other), and the sound pass never
stacks two hits on one moment (caption pops are skipped near a whoosh or the hook hit).

Some other cards also exclude each other (two hooks, two caption styles, two outros, or effects that
fight for the same spot). Those pairs are listed in each card's `avoid_with`.

## House styles and signature rotation

`styles/presets.json` maps 14 business types (cafe, trades, salon, ...) to a starting house style: a 5-6 card
`default_mix`, 3 `signature` moves, pacing and a sound card. Setup applies one with `scripts/rr.py house-style --apply`.
Each reel gets exactly ONE signature card (`scripts/rr.py next-signature`); it rotates across reels, never stacks within one.
Neighbouring types never share a hook, caption, sound or signature lead; `styleguide/build.py --check` enforces that and `avoid_with`.

## Card schema

One JSON file per card in `styles/cards/<id>.json`:

```json
{
  "id": "H1",
  "category": "hook|captions|layout|proof|broll|signature|motion|outro|sound",
  "name": "Chunky title behind head",
  "oneliner": "One sentence, shown on hover and in lists.",
  "description": "Two lines max, plain English, for the card face.",
  "prompt": "The full instruction Claude follows when rendering.",
  "engine": "captions|overlay|cut|motion|composite|sound",
  "needs": ["matting", "transcript", "assets:logo", "assets:music", "broll"],
  "pairs_with": ["C1"],
  "avoid_with": ["X3"],
  "sketch": "sketches/H1.svg",
  "duration_hint": "first 3s"
}
```

| Field | Notes |
|---|---|
| `id` | Category letter + number: H hook, C captions, L layout, P proof, B b-roll, X signature, M motion, O outro, S sound. File name must match. |
| `engine` | Which part of the pipeline renders it: `captions` (caption burner), `overlay` (HyperFrames graphics), `cut` (EDL / ffmpeg), `motion` (transitions, zooms, ramps), `composite` (matting + layering), `sound` (`engines/sound.py`: voice polish, SFX, bed, music). |
| `needs` | What must exist first. `matting` = subject cut-out, `transcript` = word timestamps, `assets:logo` / `assets:music` = files in `assets/`, `broll` = extra footage or photos. |
| `pairs_with` / `avoid_with` | Card ids. Keep `avoid_with` symmetric (if A avoids B, B avoids A). |
| `sketch` | Path relative to `styles/`. |

## Sketches

`styles/sketches/<id>.svg` is a 90x160 wireframe of a 9:16 phone: grey head-and-shoulders silhouette,
the effect drawn in simple shapes, one yellow accent, a tiny id label, nothing else. Keep each file under
2 KB and use the shared class names so the page can theme them:

`s` screen, `f` frame, `p` person, `g` grey shape, `w` white, `c` white card with outline, `k` ink,
`y` yellow, `d` dark overlay, `ys`/`ks`/`kt`/`gs`/`ws` strokes, `t` label. Put a `<style>` block in the
file for standalone viewing; the page strips it and applies its own. Clip paths must use an id unique to
the card (e.g. `qH1`).

## Adding a card

1. Copy a card from the same category to `styles/cards/<NEW_ID>.json` and rewrite every field.
2. Write the prompt like a brief to an editor: position (x/y on 1080x1920), size, color tokens,
   timing and easing, when it triggers, how long it holds, and at least one "Do NOT".
3. Draw `styles/sketches/<NEW_ID>.svg` (copy a similar sketch as a starting point).
4. Update `avoid_with` on both sides, and `pairs_with` where it helps.
5. Rebuild and check it: `python3 styleguide/build.py` (validates every card; `--check` validates only).
6. Add the card to the table below.

## Ready-made mixes

Defined in `styles/mixes.json` and shown on the page.

| Mix | For | Cards |
|---|---|---|
| Cafe story | Cafe or bakery owner telling a story | H1 + C1 + L1 + B1 + O1 + S4 |
| What to order | Restaurant menu or new-item drop | H2 + C2 + B4 + M2 + O3 + S2 |
| Salon glow-up | Salon, barber or beauty before/after | H5 + C6 + P2 + M1 + O1 + S2 |
| Job walk | Contractor or trades showing the work | H4 + C4 + L3 + B1 + O3 + S1 |
| Listing tour | Realtor showing a home | H6 + C6 + L1 + P4 + X4 + O1 + S3 |

## All cards

| ID | Name | Category | One-liner |
|---|---|---|---|
| H1 | Chunky title behind head | Hook | A big bold title sits behind you; you stay cut out in front. |
| H2 | Sticker hook with logo | Hook | Your logo and a punchy line slap on like a sticker in second one. |
| H3 | Handwritten arrow note | Hook | A scribbled arrow and note point at what you're talking about. |
| H4 | The number | Hook | A big stat counts up over your first line as you say it. |
| H5 | Before / after split | Hook | A wipe reveals the before and after in the first two seconds. |
| H6 | Question card | Hook | Your opening question appears as a clean card on screen. |
| C1 | Bold white + accent word | Captions | Chunky white captions with one word in an italic accent serif. |
| C2 | Warm typewriter | Captions | Words type on in a warm serif as you speak them. |
| C3 | Karaoke fill | Captions | Each word lights up the moment you say it. |
| C4 | Subtitle bar | Captions | Clean captions in a solid bar, like TV subtitles. |
| C5 | Keyword pop | Captions | Quiet captions, then one key word punches up huge. |
| C6 | Minimal clean | Captions | Quiet, elegant captions. No effects, just great type. |
| L1 | Name + business lower-third | Layout | Your name and business slide in when you introduce yourself. |
| L2 | Picture-in-picture corner | Layout | B-roll plays in a rounded corner window while you keep talking. |
| L3 | Split screen | Layout | You on top, the footage on the bottom, at the same time. |
| L4 | Framed on brand paper | Layout | Your video sits in a soft frame on a brand-color paper backdrop. |
| P1 | Pinned review banner | Proof | A real customer review pinned at the top like a top comment. |
| P2 | Review card stack | Proof | Star-review cards deal in one by one next to you. |
| P3 | Results / price grid | Proof | A tidy grid of your prices, packages or results. |
| P4 | Map pin + address | Proof | A pin drops on a clean little map, with your address. |
| B1 | Cutaway on every noun | B-roll | Every 6-8 seconds, cut to footage of what you're talking about. |
| B2 | Slow push-in on photos | B-roll | Your still photos slowly push in, documentary style. |
| B3 | Product pop card | B-roll | A photo of the product pops up beside you when you name it. |
| B4 | Menu moment | B-roll | Item and price land on a little menu card as you say them. |
| X1 | Orbit | Signature | Phone-screen cards orbit around you, passing behind and in front. |
| X2 | Wall collage | Signature | A wall of your own photos fills the background behind you. |
| X3 | Headline behind you | Signature | Huge words swap behind your head as each point lands. |
| X4 | Frame break | Signature | The shot shrinks into a phone and you pop out of the frame. |
| X5 | UI world | Signature | Your background becomes your own website or booking page. |
| X6 | Spotlight | Signature | Everything dims except you, like a stage light. |
| M1 | Punch-in on new sentences | Motion + pace | A subtle zoom-in at the start of each new sentence. |
| M2 | Soft crossfade + whoosh | Motion + pace | 8-frame crossfades with a soft whoosh on every scene change. |
| M3 | Speed-ramp intro | Motion + pace | The first second whips in fast, then lands at normal speed. |
| O1 | End card | Outro | Logo, address and one clear call to action to finish. |
| O2 | Follow for part 2 | Outro | A 'Part 2' teaser card that gives people a reason to follow. |
| O3 | QR + website outro | Outro | Your website and a scannable QR code to close. |
| S1 | Clean | Sound | Polished voice and a quiet room-tone bed. Nothing you'd notice, just better. |
| S2 | Punchy | Sound | Whoosh on every cut, a pop on every caption, and a riser that hits at the end of the hook. |
| S3 | Cinematic | Sound | Sweeping whooshes, a riser into a deep hit, and long tails that breathe. |
| S4 | Calm | Sound | Warm, quiet polish for cafes and wellness. Bed and voice only, no hits. |
| S5 | Music under | Sound | Your own track from assets/music, ducked under your voice. |
