# Sound effects: origin and license

Every file in this folder is synthesised by `engines/make_sfx.py` (noise, sine tones, filters and
envelopes, fixed seed) and encoded with ffmpeg. Nothing here is downloaded, sampled or taken from a
sound library, so the files carry the kit's own MIT license (see the repo `LICENSE`).

`whoosh.mp3`, `whoosh-short.mp3`, `whoosh-cinematic.mp3`, `pop.mp3`, `click-soft.mp3`, `riser.mp3`,
`impact-bass-1.mp3`, `impact-bass-2.mp3`, `sparkle.mp3`

They are byte-for-byte copies of the same names in the `media-use` skill's bundled library
(`.claude/skills/media-use/audio/assets/sfx/`), copied here so `engines/sound.py` works without that
skill. Per-file duration and intended use: that folder's `manifest.json`.

Regenerate everything (both folders, manifest durations included) with:

```bash
python3 engines/make_sfx.py
```

Same command, same bytes on every machine. To change a sound, edit its recipe in `make_sfx.py` and
re-run; `sound.py` finds each file's transient itself, so re-timing is automatic.
