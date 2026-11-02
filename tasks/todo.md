# ReelReady build — 2026-10-28
- [x] Spec written (docs/superpowers/specs/2026-10-28-reelready-design.md)
- [x] Core: CLAUDE.md, config, installer, init, questionnaire skill, reference-study skill
- [x] Style catalog (36 cards, 5 mixes) + style guide page (verified light/dark/mobile)
- [x] Engines ported, transcription backend switch, smoke render passes (cut/render/qa; captions need >1 GB disk)
- [x] Telegram add-on (optional, 15 offline tests) + business-model doc
- [x] First client package (private, gitignored)
- [x] Integration review: 8 seams fixed, disk guard in doctor, secrets scan clean
- [x] git init + first commit (no push until Suhaas says)

## Review
- Policy call left open: captions.py drops "um"/"uh" from on-screen captions (audio untouched). Confirm or revert.
- hyperframes-helper has no upstream license file; confirm before public release.
- Telegram bridge not yet run against a real bot token or a real `claude -p`.
- Next: push to GitHub (public), record the "comment STYLES" reel, install on the first client's machine.

## v0.2 (2026-10-28, evening)
- [x] Rebrand to "ReelReady by Suhaas Builds" (config, README, business doc, spec, fallbacks); Thrive Labs kept as `brand.service`
- [x] engines/story.py + reelready-edit/references/story.md: reorder/select sentences verbatim, verified on smoke (draft_story.mp4 plays hook-first)
- [x] reelready-copy skill (hooks, caption, CTA, hashtags, all DRAFT-flagged)
- [x] Sound layer: S1-S5 cards, engines/sound.py, sfx + attribution, smoke step, mixes get one S card
- [x] Wire story pass into reelready-edit SKILL.md step 2.5 + CLAUDE.md pipeline
- [x] Verify: styleguide --check (41 cards), smoke end to end, secrets scan, no clients/ tracked
- [ ] Confirm Suhaas Builds channel URL (placeholder: youtube.com/@suhaasbuilds)

## v0.3 taste layer (2026-10-28, night)
- [x] engines/captions.py: --font/--font-family/--font-weight, writes captioned.captions.json (verified Inter vs Impact frames)
- [x] styles/presets.json: 14 business types -> default mix + 3 signature moves + sound + pacing; build.py --check validates them
- [x] scripts/rr.py house-style / next-signature; profile.house_style; setup step F; edit skill rotates the signature per reel
- [x] engines/taste.py: 6 rules, TASTE PASS/FAIL; fixtures prove it passes on-brand and fails generic; smoke step
- [x] Edit skill: Brand choices block in plan.md, taste gate in QA; CLAUDE.md pipeline + hard rule 4
- [ ] Open: fixture profile uses H1 as a signature id (works, but real presets use X/M/P/B); Pixabay SFX license read; channel URL confirm

## v0.4 script writer (2026-11-01)
Design: docs/superpowers/specs/2026-11-01-reelready-script-design.md (the "Settled" section wins).
- [x] Shared banned list `engines/banned.txt`; copy skill points at it
- [x] Fixtures in tests/smoke/fixtures/script/: 2 good, 8 bad (invented price, borrowed price, spelled number, banned, fake past-reel quote, fake today quote, unflagged, too long)
- [x] `engines/script_check.py`: 9 rules; checks past-reel quotes against real transcripts, today's quotes against the owner's notes file (--chat), prices must match sourced prices
- [x] `reelready-script` skill: ideas mode, fact interview (max 3 questions a round, 2 rounds), voice from last 5 transcripts, draft in work/, check, save on "go"
- [x] Edit hand-off: offers unfilmed scripts, reuses folder, structure + hook as story hints, captions stay verbatim
- [x] Wiring: CLAUDE.md, engines/README.md (nine contracts), profile `script` block, architecture, README, smoke step
- [x] Verify: SMOKE OK twice; 3 dry runs by fresh agents (cafe with past reel, bookshop with empty profile, bookshop re-run after fixes) all PASS and saved where the skill says; style guide check ok; secrets scan clean

## Review (v0.4)
- Three dry runs found 20+ unclear spots in the first skill draft; all fixed. Biggest: facts from today's chat were taken on trust, now checked against the owner's verbatim notes file.
- Still judgment-only (not machine-checked): claims in direction beats without numbers ("say it's free"), rule-of-three lists, closing morals. The skill lists them as eye checks.
- The script's "about n s" estimate is not checked against the length budget; the budget uses profile.script.seconds.
- Open before public release: tasks/todo.md (this file) names a client in the v0.1 section and is in git history; scrub before pushing. Calm sound preset whooshes on every sentence join (found on a real reel test). Pixabay SFX license read; channel URL confirm.
