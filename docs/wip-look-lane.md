# Look lane (v0.5 parts 2 + 3): status

## Done (all committed, all verified)
- 2a `scripts/brand_from_site.py <url|index.html> [--out]`: colours, palette, fonts, logo candidates from a
  site's own CSS; downloads nothing. Wired into reelready-setup as step 4b.
- 2b `rr.py fonts [--profile P] [--yes]`: Google Fonts (OFL, TTF) into assets/fonts, records
  `brand.fonts.files` + `faces`, never overwrites. doctor lists brand fonts.
- 2c `rr.py recommend-accent`: caption emphasis colour from the brand, with the reason. Setup offers it.
- 3a `captions.py --emphasis group` (+ `--emphasis-font/-family/-words`): one word per group in a second face.
- 3b `engines/overlays.py`: hook, lower_third, polaroid, end_card from profile tokens; sidecar `.overlays.json`.
- 3c Cards H7, L5, O4, B5, mix "Brand story"; `styleguide/build.py --check` passes; index.html rebuilt.
- 3d `taste.py --overlays`: overlay-fonts, overlay-colors.
- 3e engines/README, reelready-edit SKILL, CLAUDE.md engine map, profile README.
- Proof: `bash tests/smoke/overlays.sh [out_dir]` prints OVERLAYS OK (QA PASS + TASTE PASS for both
  fixtures in tests/fixtures/brands/); `bash tests/smoke/run.sh` still prints SMOKE OK.

## Left
- Nothing required by the lane. Optional: a 16:9 / 4:5 layout for overlays.py (9:16 only today);
  overlays.sh is a separate script (about 2 minutes), not a run.sh step.

## Resume
Run both smoke scripts with `PYTHON=<repo>/.venv/bin/python` (the worktree has no .venv of its own).
