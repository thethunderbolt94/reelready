# Optional paid transcription key (AssemblyAI or ElevenLabs)

Only when the owner asks ("I have an AssemblyAI key", "use my key"). Free local captions are the
default and are fine.

The key must never be pasted into this chat, appear in a command line, or be repeated. It goes
straight into `<main folder>/.reelready/.env` through `rr.py set-key`, which reads stdin.

1. "Please don't paste the key here. I'll give you one line to paste in Terminal instead."
   (If they already pasted it: don't repeat it or use it. Say "To be safe, make a fresh key on
   their website and use that one in the next step.")
2. "Open Terminal (Cmd + Space, type Terminal, Enter; on Windows the Ubuntu window). Paste this
   line and press Enter:"
   `cd "<repo>" && python3 scripts/rr.py set-key <assemblyai|elevenlabs>`
   "It asks for your key. Paste it and press Enter. It won't show on screen, that's normal. It
   should say 'Saved'."
3. Check without showing it: `grep -c '^<ASSEMBLYAI_API_KEY|ELEVENLABS_API_KEY>=' "<env_file>"`
   (prints 1). Then save `{"transcription": {"backend": "<assemblyai|elevenlabs>", "key_stored": true}}`
   with profile-merge and say "Saved privately on your computer."

Never write the key to the profile, plan files, exports, logs or the repo.
