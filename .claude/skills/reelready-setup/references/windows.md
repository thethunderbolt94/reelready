# Windows (via WSL)

ReelReady runs inside WSL (Ubuntu on Windows). One step per message; wait for "done" each time.
The owner types the commands; you never run sudo.

1. "ReelReady runs inside a free Windows add-on called Ubuntu (WSL). It's a one-time setup: about
   20 minutes and one restart. Shall we do it?"
2. "Click Start, type **PowerShell**, right-click it and choose **Run as administrator**. Paste
   `wsl --install` and press Enter. When it finishes, restart your PC and tell me."
3. "After the restart an Ubuntu window opens and asks for a new username and password. Pick
   anything simple and write the password down. Tell me when you see a prompt ending in $."
4. "In the Ubuntu window, paste this and press Enter (type your Ubuntu password when asked):
   `sudo apt update && sudo apt install -y ffmpeg nodejs npm python3-venv`"
5. "Now install Claude Code in Ubuntu. Paste: `curl -fsSL https://claude.ai/install.sh | bash`"
6. Turn this kit's Windows path into its Ubuntu path (`C:\Users\Ana\Downloads\reelready` ->
   `/mnt/c/Users/Ana/Downloads/reelready`; in Git Bash `pwd` shows `/c/Users/...`, so add `/mnt`).
   "Paste: `cd "/mnt/c/Users/<you>/.../reelready" && claude` then say **set up reelready** there."

Inside WSL (`grep -qi microsoft /proc/version` succeeds), setup carries on from A. Main folder
default, so it shows on the Windows Desktop:
`/mnt/c/Users/<windows user>/Desktop/AI Video Editor`, where the user is
`cmd.exe /c 'echo %USERNAME%' 2>/dev/null | tr -d '\r'`. Open it with
`explorer.exe "$(wslpath -w "<path>")"`.
