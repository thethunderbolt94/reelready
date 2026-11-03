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
- Telegram bridge not yet run against a real bot token or a real `claude -p`.
- Next: push to GitHub (public), record the "comment STYLES" reel, install on the first client's machine.

## v0.2 (2026-10-28, evening)
- [x] Rebrand to "ReelReady by Suhaas Builds" (config, README, business doc, spec, fallbacks); Thrive Labs kept as `brand.service`
- [x] engines/story.py + reelready-edit/references/story.md: reorder/select sentences verbatim, verified on smoke (draft_story.mp4 plays hook-first)
- [x] reelready-copy skill (hooks, caption, CTA, hashtags, all DRAFT-flagged)
- [x] Sound layer: S1-S5 cards, engines/sound.py, sfx + attribution, smoke step, mixes get one S card
- [x] Wire story pass into reelready-edit SKILL.md step 2.5 + CLAUDE.md pipeline
- [x] Verify: styleguide --check (41 cards), smoke end to end, secrets scan, no clients/ tracked
- [x] Suhaas Builds channel URL confirmed by owner 2026-11-02 (youtube.com/@suhaasbuilds)

## v0.3 taste layer (2026-10-28, night)
- [x] engines/captions.py: --font/--font-family/--font-weight, writes captioned.captions.json (verified Inter vs Impact frames)
- [x] styles/presets.json: 14 business types -> default mix + 3 signature moves + sound + pacing; build.py --check validates them
- [x] scripts/rr.py house-style / next-signature; profile.house_style; setup step F; edit skill rotates the signature per reel
- [x] engines/taste.py: 6 rules, TASTE PASS/FAIL; fixtures prove it passes on-brand and fails generic; smoke step
- [x] Edit skill: Brand choices block in plan.md, taste gate in QA; CLAUDE.md pipeline + hard rule 4
- [ ] Open: fixture profile uses H1 as a signature id (works, but real presets use X/M/P/B)

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
- Open before public release: see the pre-push audit below.

## Pre-push audit (2026-11-02)
- [x] Secrets sweep of every file in every commit: no real keys, tokens or private keys (only fake test tokens)
- [x] Every engine flag and rr.py command named in skills and docs exists
- [x] Independent reviews of all six ReelReady skills; 37 findings fixed (setup 15, edit/styles 12, copy/script 10)
- [x] Script checker hardened: numbers only from checked sources, owner's own words exempt from banned list, superlatives banned, post copy mode (COPY PASS)
- [x] Sound: calm adds no whooshes; others only on jump cuts, 2.5 s apart; sound uses the story EDL
- [x] rr.py run / doctor find Homebrew tools on a fresh Mac; set-key hides the pasted key
- [x] SMOKE OK, style guide check ok, private-data scan clean
- [x] Pixabay SFX replaced: all 19 sounds synthesised by engines/make_sfx.py (MIT, deterministic); manifest durations refreshed
- [x] Commit author on main rewritten to the Thrive Labs address (backup branch kept locally, never pushed); Apache-2.0 text copied into each HyperFrames skill folder
- [x] hyperframes-helper removed (unused, no upstream licence)
- [x] Channel URL confirmed; nothing left to decide before a public push
