# Install help (Mac first, then Linux / WSL)

One step per message. Wait for "done" before the next step. Never use sudo yourself.

## 1. Mac: "command line developer tools" box

A fresh Mac asks for these the first time `python3` runs. Say:
"A box just popped up asking to install developer tools. Please click **Install** (not 'Get
Xcode'). It takes about 5-10 minutes. Tell me when it says done."
Then re-run `python3 scripts/doctor.py`. If no box appeared, run `xcode-select --install` to show it.

## 2. Mac: Homebrew (it needs their Mac password, so they run it)

1. "I need one free tool called Homebrew that installs the video tools. It asks for your Mac
   password, so you'll paste one line. Ready?"
2. "Press Cmd + Space, type **Terminal**, press Enter."
3. "Paste this line and press Enter. Type your Mac password when asked (nothing shows while you
   type, that's normal), then press Enter again:"
   `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
4. "Tell me when it says 'Installation successful'." (It may say the account isn't an admin: then
   an admin of that Mac has to run it.)
5. Then run setup (SKILL.md A).

## 3. Mac: Homebrew installed but tools "not found"

On Apple Silicon Homebrew lives in `/opt/homebrew/bin`, which this session may not see yet. If
`/opt/homebrew/bin/brew` exists but `command -v brew` prints nothing:
- For the rest of this session, start every command with `eval "$(/opt/homebrew/bin/brew shellenv)" && `.
- Ask: "Can I add one line to your Mac's terminal settings (a file called .zprofile) so the video
  tools are always found? It only tells your Mac where Homebrew lives." Only on yes:
  `grep -qs 'brew shellenv' ~/.zprofile || echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile`
  No -> keep using the prefix. If a later session's doctor shows ffmpeg missing, ask again.

## 4. No internet

FAILED lines with "could not resolve host", "timed out", "network" or "SSL": say
"I can't reach the internet to download the tools. Could you check your Wi-Fi and say 'try again'?"
Carry on with B-D meanwhile. setup.sh is safe to run again; never loop it on your own.

## 5. Linux / WSL without Homebrew

setup.sh prints a `YOU DO` line with `sudo apt install ...`. Give them exactly that line to paste
into their terminal (it asks for their password), wait for "done", run setup again.
