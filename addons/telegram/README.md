# ReelReady Telegram add-on

Record a video on your phone, send it to your own Telegram bot, and the edited video comes back in the same chat. Off by default. Everything runs on your computer.

You do not need to type commands. Tell Claude: **"set up the Telegram add-on"** and it walks you through the steps below.

## Set up (6 steps)

1. **Make a bot.** In Telegram, open a chat with `@BotFather`, send `/newbot`, pick a name, and copy the token it gives you (a long string with a colon in it). Treat it like a password.
2. **Give Claude the token.** When Claude asks, paste it in the chat. Claude saves it to `<main folder>/.reelready/.env` as `TELEGRAM_BOT_TOKEN`. It goes nowhere else.
3. **Find your chat id.** Send any message to your new bot. Claude runs `bridge.py --find-chat-id` and reads your number from the result.
4. **Lock it to you.** Claude saves that number as `TELEGRAM_ALLOWED_CHAT_IDS` in the same `.env` file. Add more numbers, separated by commas, for teammates.
5. **Start the bridge.** Claude installs the one Python helper it needs (`requests`) and runs `addons/telegram/start.sh`. To keep it running after restarts, see "Run it in the background" below.
6. **Send a test clip.** Film 10 seconds, send it to the bot. You should see "Got it, editing…" and then your finished video with a short summary.

## How it works

1. A small script (`bridge.py`) asks Telegram every few seconds, "anything new?" (long polling, so no public server or open port is needed).
2. A video from an allowed chat is saved into `raw footage/` as `<timestamp>-telegram.mp4`.
3. The bridge replies "Got it, editing…" and writes a job file to `.reelready/work/jobs/`.
4. It runs Claude Code headless in your main folder: `claude -p "edit the newest clip in raw footage, use my default mix, just do it"`.
5. It finds the newest `exports/<date>-<name>/final.mp4` made during that run and sends it back with the 3-line summary.
6. A text message after a video is passed on as the instruction for the most recent clip. Example: `use styles H1+C2`.

If something fails, the bridge replies in plain language and your original clip stays in `raw footage/`.

### Settings (all optional, in `.reelready/.env`)

| Setting | Default | Meaning |
|---|---|---|
| `REELREADY_CLAUDE_CMD` | `claude -p` | Command used for each edit. The prompt is added as the last argument. |
| `REELREADY_JOB_TIMEOUT` | `1800` | Seconds before an edit is stopped. |
| `REELREADY_MAX_UPLOAD_BYTES` | `49000000` | Bigger exports are shrunk with ffmpeg first. |
| `TELEGRAM_API_BASE` | Telegram cloud | Point at a local Bot API server to lift the size limits below. |

Because the edit runs unattended, Claude Code needs permission to read and write inside your main folder without asking. Claude will set `REELREADY_CLAUDE_CMD` to something like `claude -p --permission-mode acceptEdits` if your setup needs it.

## Limits

- **Download from phone: about 20 MB.** Telegram's public bot service refuses to hand bots larger files. A normal video send (Telegram shrinks it on your phone) usually fits for clips up to about a minute. Sending "as a file" keeps full quality, so only use that trick for short clips. Longer or heavier clips: trim them, or drop them straight into `raw footage/` (AirDrop, cable, cloud folder).
- **Upload back to you: 50 MB.** If the export is bigger, the bridge re-encodes a copy with ffmpeg (`-crf 28`, then a smaller size if still too big) and sends that. The full-quality file always stays in `exports/`.
- **One edit at a time.** Messages sent while an edit is running wait their turn.
- **Your computer must be on** and awake. The bridge cannot edit while the Mac is asleep.
- Advanced: running Telegram's own Bot API server locally removes the 20 MB and 50 MB limits. Set `TELEGRAM_API_BASE` to its address.

## Security

- **Allowlist only.** The bridge acts only on messages from chat ids in `TELEGRAM_ALLOWED_CHAT_IDS`. Anyone else gets no reply, no download, and no way to trigger Claude. If the list is empty the bridge refuses to start.
- **Text messages from allowed chats become instructions to Claude.** Only allow people you trust with your editing folder.
- **The token lives only in `.reelready/.env`.** Never paste it into a public place, commit it, or put it in the launchd file. If it leaks, message `@BotFather`, send `/revoke`, and update `.env`.
- The bridge hides the token in its own error messages and log lines.
- Make sure `.reelready/` is in your `.gitignore` if you keep this folder in git.

## Run it in the background (macOS)

Quick way, until you restart the computer:

```
addons/telegram/start.sh "/path/to/AI Video Editor"
addons/telegram/stop.sh  "/path/to/AI Video Editor"
```

Log file: `.reelready/work/telegram.log`.

Always-on way (starts at login, restarts itself if it stops). Ask Claude "keep the Telegram bridge running all the time", or do it by hand:

1. Copy `com.reelready.telegram.plist.template` to `~/Library/LaunchAgents/com.reelready.telegram.plist`.
2. Replace `__PYTHON__` (output of `which python3`), `__BRIDGE__` (full path to `bridge.py`), `__MAIN_FOLDER__`, and `__HOME__` (your home folder).
3. Load it: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.reelready.telegram.plist`

To stop it for good:

```
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.reelready.telegram.plist
```

Delete the plist file to stop it from coming back at next login. Run `stop.sh` first if you also used the quick way.

## Testing without Telegram

```
python3 addons/telegram/bridge.py --main-folder "/path/to/AI Video Editor" --dry-run \
  --updates-file addons/telegram/tests/fake_updates.json
python3 -m unittest discover -s addons/telegram/tests -v
```

`--dry-run` fakes the Claude call (it copies the newest clip to a fake export). With `--updates-file` it also fakes Telegram, so no token or network is needed.
