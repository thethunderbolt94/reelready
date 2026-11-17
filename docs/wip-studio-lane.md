# WIP: Studio app lane (v0.5 parts 4 and 5)

## Done (committed)
- Sorter: `scripts/sorter.py`, `rr.py sort [--dry-run] [--undo [BATCH]] [--resort] [--json] [--quiet]`.
  Groups, moves logged to `.reelready/sort-log.jsonl`, never renames/deletes/overwrites (clash left in place),
  `library.json` + thumbnails in `.reelready/work/library/thumbs/`. Speech: ffmpeg astats (loudness + zero-crossing
  variation) decides clear cases; unsure clips go to faster-whisper's VAD, then a cached Whisper model (never downloads).
  50 mixed files sorted in 1.4 s cold; undo restores paths, sizes, mtimes and content exactly.
- Studio: `studio/serve.py` (127.0.0.1 only, Host/Origin/JSON checks, Range support, media only from raw footage,
  exports, assets, references, .reelready/work; never .env), `studio/index.html|studio.css|studio.js`
  (#library with the sort animation, #review, #styles iframe). `styleguide/serve.py` is a wrapper on #styles.
- Review contract: `scripts/review.py`, `rr.py review-request`, `rr.py wait-review` (0 / 2 timeout / 3 incomplete);
  documented in `engines/README.md`; edit skill step 3.5.
- `rr.py studio --start|--stop`, SessionStart hook in `.claude/settings.json`, CLAUDE.md "Session start".
- Folder contract text (CLAUDE.md, README, init.py README, skills), `rr.py newest` and telegram `newest_clip`
  search group folders.
- `tests/smoke/studio.sh` passes (STUDIO PASS); called from `tests/smoke/run.sh`.
- Checked in a real browser (desktop + 375 px, light + dark): sort moment, grid, review flow end to end.

## Left
- Confirm the full `bash tests/smoke/run.sh` prints SMOKE OK (it was running when this was written).
- Split the wip commit into logical commits if wanted.
- Optional: README tour screenshots (part 7).

## Resume
`bash tests/smoke/studio.sh` (fast) then `bash tests/smoke/run.sh`. Try the app:
`REELREADY_HOME=<test main folder> python3 studio/serve.py --no-open` and open http://localhost:4810/#library.
