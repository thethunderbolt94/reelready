# Sound effects: origin and license

These files are byte-for-byte copies of the bundled SFX library in the `media-use` skill
(`.claude/skills/media-use/audio/assets/sfx/`), copied here so `engines/sound.py` works without that skill:

`whoosh.mp3`, `whoosh-short.mp3`, `whoosh-cinematic.mp3`, `pop.mp3`, `click-soft.mp3`, `riser.mp3`,
`impact-bass-1.mp3`, `impact-bass-2.mp3`, `sparkle.mp3`

## Source and license (as stated by the media-use skill)

The skill's `audio/assets/sfx/CREDITS.md` says all of its sound effects are sourced from
[Pixabay](https://pixabay.com/sound-effects/) and used under the
[Pixabay Content License](https://pixabay.com/service/license-summary/), which (per that file) allows
commercial and non-commercial use, modification, and redistribution inside derivative works such as
rendered videos, with no attribution required. Attribution is given here for transparency.

## What we could not confirm

- `CREDITS.md` names Pixabay as the source but gives no per-file Pixabay page, author or upload ID, so
  the individual origin of each file cannot be traced from this repo.
- Our reading of the Pixabay Content License (not checked against the live page) is that it covers
  use inside videos but restricts distributing the sound files on their own, as standalone files. Shipping them
  inside this kit is the same arrangement the media-use skill already uses, but it is a judgement call, not something this repo can verify.
- `whoosh.mp3` and `whoosh-short.mp3` are identical files in the source library (same bytes).
  `sound.py` makes the "short" variant shorter by trimming its tail.

Per-file duration and intended use: `.claude/skills/media-use/audio/assets/sfx/manifest.json`.
