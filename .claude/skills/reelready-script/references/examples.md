# Worked examples

The first two examples are the generated mode (only on "just write it for me"). The third is the default interview. All pass `engines/script_check.py`. Businesses are made up.

## 1. Cafe, talking points, from a past reel

Profile: Corner Bean Coffee, Anytown, tone warm / unhurried / local, `copy.cta` "Visit us",
`script.seconds` 30. One past reel, folder `2026-10-28-tuesday-roast`, where the owner said:
"We roast our beans right here, every Tuesday morning. Most people don't know the back room is a
roaster. And on Saturdays the almond croissants come out at eight."

Owner today: "script for the croissants".

```
DRAFT - written by AI. Change anything that doesn't sound like you.

# Script: almond croissant Saturdays
Corner Bean Coffee · structure: hook, context, payoff · format: talking-points · about 25 s · 9:16

## Hook  [GENERATED - approve?]
"Saturdays at eight, these come out."

## Beats  [GENERATED - approve?]
1. Show the tray. Say what they are.
2. "Most people don't know the back room is a roaster."
3. "Visit us Saturday morning."

## Film this
- A-roll: you at the counter, phone at eye level, window light on your face.
- B-roll: the tray coming out (3 s), one croissant close up (2 s), the roaster door (2 s).

## Facts used
- almond croissants come out Saturdays at eight | your past reel 2026-10-28-tuesday-roast: "the almond croissants come out at eight"
- the back room is a roaster | your past reel 2026-10-28-tuesday-roast: "the back room is a roaster"
- Visit us | profile copy.cta

## Not used
- price, how many you bake (you didn't tell me)
```

Not allowed here: "$4 each" (price never given, so it goes under Not used), "best croissants in
Anytown" (superlative not said), "baked fresh every morning" (only Saturdays was said),
"Hi, I'm Sam from Corner Bean" as the opening (greeting never opens).

## 2. Plumber, word for word, before and after

Profile: Hartley Plumbing, Anytown, `business.what_we_do` "Emergency and same-day plumbing repairs",
tone direct / calm, `copy.cta` "Call us", `script.seconds` 25. No past reels yet. The owner asked
for exact words. The skill asked two questions: "What was the job?" and "How long did it take?"

Owner today: "Burst pipe under a kitchen sink on Monday, water everywhere. Fixed in forty minutes,
no damage to the cabinet."

```
DRAFT - written by AI. Change anything that doesn't sound like you.

# Script: burst pipe, forty minutes
Hartley Plumbing · structure: before, after · format: word-for-word · about 20 s · 9:16

## Hook  [GENERATED - approve?]
Fixed in forty minutes. Cabinet still dry.

## Beats  [GENERATED - approve?]
1. Monday, this kitchen had water everywhere.
2. A burst pipe right under the sink.
3. We do same-day repairs.
4. If a pipe goes at your place, call us.

## Film this
- A-roll: you kneeling by the open cabinet, phone at chest height, cabinet light on.
- B-roll: the new pipe joint close up (3 s), a dry hand on the cabinet floor (2 s), van door closing (2 s).

## Facts used
- fixed in forty minutes | you told me today: "fixed in forty minutes"
- no damage to the cabinet | you told me today: "no damage to the cabinet"
- Monday, burst pipe under the kitchen sink | you told me today: "burst pipe under a kitchen sink on Monday"
- same-day repairs | profile business.what_we_do
- call us | profile copy.cta

## Not used
- price of the job, the customer's name or street (you didn't tell me)
```

The check notes three facts that rest only on today's chat, so the skill tells the owner in one
line: "Three facts come only from what you told me today: the forty minutes, the dry cabinet and
the Monday job. Make sure they're right." Not allowed here: "24/7" (never said), "Anytown's most
trusted plumber" (superlative), "Don't wait until it's too late" (fake urgency).


## 3. Barber, interview (the default), talking points

Business: Maple Street Barbers, Anytown. The owner named a topic ("kids haircut Saturdays"). The
skill asked 7 short questions, one or two per message, and saved each answer untouched to
`answers.json`:

- A1  Q: What is it, in a sentence?
      A: "Saturday mornings we do kids haircuts with no appointment. You just walk in and sit down."
- A2  Q: Who is it for?
      A: "It's for parents who dread the haircut meltdown. Most of our kids are four to eight."
- A3  Q: Tell me about a moment that really happened.
      A: "Last week a little boy fell asleep in the chair halfway through his fade. We just turned the clippers off and let him finish his nap."
- A4  Q: What do people say about it?
      A: "People say it's the only place their son sits still."
- A5  Q: What is a detail only you would know?
      A: "We keep a jar of stickers by the mirror and the kids pick one before they pay."
- A6  Q: Why does it matter to you?
      A: "My dad cut my hair on his kitchen floor, so I know how scary the first haircut feels."
- A7  Q: How do people find you?
      A: "Come by Maple Street any Saturday morning. The door's open from eight."

The script is those answers, picked and ordered (hook, context, payoff). The hook is the most
concrete moment (A3); the clipper line travels right after it because it finishes the story; the
invite closes. A2 and A6 are left out, listed under Not used. Nothing was added to any span.

```
DRAFT - written by AI. Every spoken line is your own words from your answers. Only the order and the picks are ours, so check them.

# Script: kids haircut Saturdays
Maple Street Barbers · structure: hook, context, payoff · format: talking-points · source: answers · about 25 s · 9:16

## Hook
"A little boy fell asleep in the chair." (A3)

## Beats
1. "We just turned the clippers off and let him finish his nap." (A3)
2. "Saturday mornings we do kids haircuts with no appointment." (A1)
3. "People say it's the only place their son sits still." (A4)
4. "We keep a jar of stickers by the mirror and the kids pick one before they pay." (A5)
5. "Come by Maple Street any Saturday morning." (A7)

## Film this
- A-roll: you beside the chair, phone at eye level, window light on your face.
- B-roll: the empty chair (2 s), the sticker jar by the mirror (3 s), the shop door (2 s).

## Not used
- A2 (who it is for), A6 (why it matters): kept for a longer cut.
```

`engines/script_check.py` prints `SCRIPT PASS (7 rules)` with `answers-only` ok. It also prints a
note that "the only" is on the banned list: that is her own phrase in A4, so it stays and the owner
is told. Not allowed here: "A little boy fell asleep in the barber chair" (one word added, fails
`answers-only`), a line with no `(A<n>)`, or one that joins the end of A1 to the start of A5.
