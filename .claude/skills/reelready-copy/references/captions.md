# Post caption, CTA, hashtags

## Caption: 2 to 4 short lines

1. **Line 1, the point.** The one thing this reel is about, close to how the owner said it.
   It can echo the chosen hook but shouldn't copy it word for word.
2. **Lines 2-3, one or two concrete details** from the transcript: what, where, when, who, as said.
   Two points maximum. Stop when the facts run out.
3. CTA goes in its own section, not in the caption.

Pasted order in the app: caption, blank line, CTA, blank line, hashtags.

## Voice

- Tone words from `profile.tone` (default warm, direct, local). Warm = "we", "you", plain thanks.
  Direct = short sentences, the fact first. Local = the street, the town, regulars, as the owner says them.
- One idea per line, 4 to 12 words each. Active voice. Words a customer uses, not marketing words.
- Let the details do the work. Don't add a closing moral ("Because quality matters.").
- Don't chain 3+ fragments ("Fresh. Local. Ours."). Join them into one natural sentence or cut.
- Read it as the owner, out loud. Caption + CTA under 10 seconds (about 25 words together).
- No emojis unless a profile tone word asks for them; then 1 at most.

## Banned words and moves

game-changer, unlock, elevate, dive in, delve, journey, curated, seamless, next level, indulge,
treat yourself, look no further, nestled, hidden gem, must-try, in today's world, it's not just X
it's Y, rule-of-three lists ("fresh, local and delicious"), em dashes, semicolons, exclamation marks,
rhetorical "Ever wondered...?" openers.

## CTA: one line, one action

Shape: action verb + what they get or where. Use `profile.copy.cta` as the base and make it fit
this reel ("Visit us" -> "Visit us on Saturday morning" if Saturday is in the reel).
No `copy.cta` -> pick by business:

| Business | CTA shape |
|---|---|
| Walk-in shop, cafe, restaurant (has a location) | Visit us / Come say hi at <place they named> |
| Bookings: salon, barber, clinic, trades | Book through the link in bio / DM us to book |
| Service or quote work | DM us "<word>" for a quote |
| Online or no shopfront | Link in bio |

Never add a deal, deadline, price or opening hours the owner didn't give. No "Like and follow",
no "Tag a friend", no "Comment below" unless the owner asked for it.

## Hashtags: 5 to 8

- **2 local**: from `business.location` (and a neighbourhood if the owner named one):
  `#anytown`, `#anytowncafe` / `#anytowneats`.
- **3 to 4 niche**: what is actually in this reel: `#coffeeroaster`, `#sourdoughbread`, `#balayage`.
- **1 to 2 broad**: the category: `#coffee`, `#smallbusiness`, `#hairsalon`.
- `copy.hashtags_extra` are always included and count toward the 8.
- Lowercase, no spaces, no punctuation. One line, at the end.
- Banned: `#follow4follow`, `#followforfollow`, `#f4f`, `#like4like`, `#l4l`, `#likeforlikes`,
  `#tagsforlikes`, `#viral`, `#explorepage`, `#instagood`, `#fyp`, `#foryou`, `#foryoupage`, any
  trending tag unrelated to the reel, and any tag naming another business.
