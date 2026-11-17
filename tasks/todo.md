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
- Pushed public 2026-11-02: https://github.com/thethunderbolt94/reelready. Next: record the "comment STYLES" reel, install on the first client's machine.

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

## v0.5 Studio (planned 2026-11-17; revised after owner feedback)
Owner decisions: build the kit anyone can use first, client work later. No Windows code: Windows is a written
guide in the repo that Claude Code follows on the user's machine, installing what it needs with their OK.
Review-and-approve page, not a timeline editor. Script comes from a Q&A in the owner's own words. Caption
colour comes from the brand profile, with a recommended one when the profile has none. Push main as parts land.
Visual of this order: docs/roadmap-v0.5.html
Answered 2026-11-17: (1) Mac-only spots stay in code; the Windows guide tells Claude which four spots to patch
on the user's machine. (2) The sorter MOVES originals into labelled folders inside raw footage: never rename,
never delete, every move logged to .reelready/sort-log.jsonl, `rr.py sort --undo` restores; the folder
contract in CLAUDE.md changes to allow exactly this. (3) Studio opens on session start: new clips are sorted
and the page opens. (4) The style guide folds into the Studio app: Library, Review, Styles.

### 1. Install guide for any OS (docs only, first, small)
- [ ] INSTALL.md: per-OS table (macOS, Linux, Windows) of what Claude installs and how (brew / apt / winget),
      always with the user's OK; Windows notes: no python3 command, venv in Scripts, npx.cmd, Node 22+,
      UTF-8, main folder outside OneDrive
- [ ] reelready-setup/references/windows.md rewritten as instructions to Claude (native first, WSL plan B);
      CLAUDE.md "First run" points to it; README requirements line updated

### 2. Brand kit (setup reads the owner's brand)
- [ ] reelready-setup: "brand from your website": read the site's CSS for colours, fonts, logo; owner confirms
- [ ] rr.py fonts: download the profile's Google Fonts (OFL) into assets/fonts; doctor lists them
- [ ] Caption accent: profile captions.accent_color, else a recommended one picked from brand.colors

### 3. Branded overlays (needs 2)
- [ ] captions.py: emphasis word per group in a second font style (e.g. italic display face) + accent
- [ ] engines/overlays.py on HyperFrames, driven by profile tokens: hook card, note-card lower third,
      end card with logo/seal and CTA pill, polaroid frame for a b-roll beat
- [ ] Cards H7, L5, O4, B5 + one new mix; taste.py reads the overlays sidecar

### 4. Sorter (local app)
- [ ] rr.py sort: probe raw footage (length, orientation, shoot day, speech yes/no, photo vs video),
      groups (Talking to camera, B-roll, Voice notes, Photos, Too short), writes .reelready/library.json
      and thumbnails; moves originals into group folders inside raw footage (logged, --undo restores)
- [ ] Studio app (stdlib server, replaces styleguide/serve.py): Library page (thumbnails fly into labelled
      folders, then a grid), Styles page (the style guide), opened on session start

### 5. Review-and-approve page (same app, needs 4's shell)
- [ ] Plan cards for every generated line: Approve / Edit / Reject; caption corrections; brand choices
- [ ] Preview: draft player, trim each cut, swap a b-roll shot from the library, pick hook A/B
- [ ] Render writes <export>/review.json; the edit skill waits for it and re-renders only changed layers

### 6. Script by interview (independent)
- [ ] reelready-script interview mode: 5 to 8 short questions; the script is the owner's answers ordered,
      never a written line; each beat cites its answer; script_check answers-only rule
- [ ] Voice-memo path: a 2-minute ramble -> transcript -> story pass -> script, same rule

### 7. Proof
- [ ] Smoke test covers sort, overlays, review.json; README tour with screenshots; push main

Later (not this round): the first client's package and re-cut demo, using parts 2, 3 and 6.
