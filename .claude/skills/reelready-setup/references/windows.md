# Windows (native first, WSL as plan B)

Instructions for you, Claude. Nothing here has been tested on a real Windows PC. Treat every step
as unverified: run it, read the output, and tell the owner plainly if something does not work. The
owner is probably not technical. Plain words, one question per message, run every command yourself.
Never use administrator rights or sudo without saying so first and getting a yes.

The kit ships no Windows code. Instead you install the tools with winget and then patch a few
Mac-only spots on this machine. Those patches are local changes. Do not commit them, do not push
them, and tell the owner they exist (`git status` will show them).

## 1. Detect Windows

Windows if `uname -s` starts with `MINGW`, `MSYS` or `CYGWIN`, or `$OS` is `Windows_NT`, or Python
says `os.name == "nt"`. Inside WSL (`grep -qi microsoft /proc/version` succeeds) you are on Linux:
use the Linux table in INSTALL.md and ignore the rest of this file except the main folder note at
the end. Ask which shell the commands run in (PowerShell, cmd or Git Bash) and adapt quoting.
There is no `python3` command on Windows. Use `py -3.12` until the venv exists, then
`.venv\Scripts\python.exe`.

## 2. Ask the owner's OK

Say: "ReelReady needs four free tools: a video tool (ffmpeg), Node.js, Python and git. I'll install
them with Windows' own installer (winget). About 2 GB and 10 minutes. OK?" Wait for a yes.
Check `winget --version` first. If winget is missing, tell the owner to install "App Installer"
from the Microsoft Store, then continue. Windows may pop up a permission box: tell them to click Yes.

## 3. Install with winget (skip what is already there)

Check each with its version command first (`ffmpeg -version`, `node --version`, `py -3.12 --version`,
`git --version`). For the missing ones:

```
winget install --id Gyan.FFmpeg -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id Python.Python.3.12 -e
winget install --id Git.Git -e
```
Add `--accept-package-agreements --accept-source-agreements` only after the owner said yes to the
installs. These IDs were found in the winget catalog; none was run on Windows by us.
Node must be 22 or newer (HyperFrames needs it). If `node --version` is lower, run the winget line
again with `--upgrade`, or `winget upgrade --id OpenJS.NodeJS.LTS`.

## 4. Restart Claude Code, then set UTF-8

New installs are not on PATH in the running session. Tell the owner: "Close Claude Code and open it
again in this folder, then say 'carry on'." After the restart re-check the four version commands.
Then run `setx PYTHONUTF8 1`. It applies to new terminals only, so for this session also set it
before each Python call (PowerShell: `$env:PYTHONUTF8=1`). This makes Python read and write text
as UTF-8, which covers the missing `encoding="utf-8"` in step 7.

## 5. Create the venv and install packages

From the repo root:
```
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r engines/requirements.txt
.venv\Scripts\python.exe -m pip install yt-dlp
```
ARM PCs (Snapdragon; `echo %PROCESSOR_ARCHITECTURE%` says ARM64): faster-whisper needs CTranslate2,
which may have no wheel for Windows on ARM (unverified). If the faster-whisper install fails, do
not try to build it. Tell the owner, and offer the transcription backends the kit already has:
`assemblyai` or `elevenlabs` (key needed, paid per use; see `references/keys.md`). Install the rest
with `faster-whisper` removed from the command (`pip install requests numpy pillow librosa matplotlib`)
and save `transcription.backend` in the profile accordingly. Skip the model download below.

Warm up HyperFrames and get the Whisper model (about 480 MB, once; say so first):
```
npx --yes hyperframes --version
.venv\Scripts\python.exe -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"
```

## 6. Main folder

Default `C:\AI Video Editor`. Windows 11 often syncs the Desktop and Documents with OneDrive, which
can lock files and upload every clip, so do not put it there unless the owner asks. Ask:
"I suggest `C:\AI Video Editor`. Is that OK?" Then:
```
.venv\Scripts\python.exe scripts/init.py --path "C:\AI Video Editor"
```
Open it for them: `explorer "C:\AI Video Editor"`.

## 7. Patch the kit on this machine

Do each patch by searching for the text (line numbers drift). Make the edit, then run
`.venv\Scripts\python.exe -c "import ast,sys;ast.parse(open(sys.argv[1],encoding='utf-8').read())" <file>`
to confirm it still parses. Keep a list of what you changed for the owner.

| # | File | Search for | Replace with |
|---|---|---|---|
| 1 | `scripts/doctor.py` | `VENV_PY = REPO / ".venv" / "bin" / "python"` | `VENV_PY = REPO / ".venv" / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")` |
| 2 | `scripts/doctor.py` | `REPO / ".venv" / "bin" / "yt-dlp"` | `REPO / ".venv" / ("Scripts" if os.name == "nt" else "bin") / ("yt-dlp.exe" if os.name == "nt" else "yt-dlp")` |
| 3 | `scripts/rr.py` | `"venv_python": str(REPO / ".venv" / "bin" / "python")` | the same Scripts / python.exe expression as patch 1 |
| 4 | `scripts/rr.py` | `venv_bin = REPO / ".venv" / "bin"` | `venv_bin = REPO / ".venv" / ("Scripts" if os.name == "nt" else "bin")` |
| 5 | `engines/captions.py` | `need("ffmpeg"); need("npx")` | `need("ffmpeg"); NPX = need("npx")` (`need` returns `shutil.which`'s full path, which is `...\npx.cmd` on Windows) |
| 6 | `engines/captions.py` | `subprocess.run(["npx", "--yes", f"hyperframes@{HF_VERSION}"` | the same line starting `[NPX, "--yes", ...` so Windows can run the `.cmd` file |
| 7 | `scripts/doctor.py` | `run(["npx", "--no-install", "hyperframes", "--version"]` | `run([shutil.which("npx"), "--no-install", "hyperframes", "--version"]` |
| 8 | `scripts/doctor.py` | `add("node >= 18", bool(nv) and major(nv) >= (18, 0)` | `add("node >= 22", bool(nv) and major(nv) >= (22, 0)` (also change the label) |
| 9 | `scripts/doctor.py` | `Path.home() / ".npm" / "_npx"` | the npm cache folder: on Windows `Path(os.environ.get("LOCALAPPDATA", "")) / "npm-cache" / "_npx"` (or ask `npm config get cache`) |
| 10 | `scripts/doctor.py` and `scripts/rr.py` | the `/opt/homebrew/bin`, `/usr/local/bin` PATH lines | harmless on Windows (they only add folders that exist). Leave them. |

Notes on the table:
- Patches 1 to 4 make doctor and `rr.py run` find the venv. `rr.py run` puts the venv folder first on
  PATH, so after patch 4 plain `python` inside `rr.py run` is the venv python.
- Patch 5 and 6: `subprocess.run(["npx", ...])` fails on Windows because the real file is `npx.cmd`.
  Use the full path `shutil.which` returned. Check by running `npx --version` once from Python.
- Patch 8: doctor on Mac still says 18. Only your local copy changes.
- Text files: the kit calls `read_text()` and `write_text()` without `encoding="utf-8"` (about 40
  places across `scripts/` and `engines/`). With `PYTHONUTF8=1` from step 4 that is fine, so do NOT
  edit them all. If you ever see `UnicodeDecodeError` or garbled names in captions, the variable is
  not set in that shell: set it and re-run.
- `os.chmod(env_path, 0o600)` in `rr.py` does nothing useful on Windows (no error). Fine. Tell the
  owner their key file is protected only by their Windows login.
- Skill commands are written `python3 ...`. On Windows run them as
  `.venv\Scripts\python.exe scripts\rr.py ...`, and engines as
  `.venv\Scripts\python.exe scripts\rr.py run -- .venv\Scripts\python.exe engines\<x>.py ...`.
  In PowerShell a path with spaces needs the `&` call operator and quotes.
- `bash scripts/setup.sh` and `bash tests/smoke/run.sh` do not apply (setup.sh prints WSL
  instructions on Windows; the smoke test needs macOS `say`). Do not run them.
- Not patched, so expect trouble: any `/tmp` paths, `ffmpeg` filter paths with a drive colon
  (`C:`) which need escaping inside `-vf` strings, and fonts. If `captions.py --font` or a filter
  fails on a path, tell the owner and fall back to the default look.

Then say: "I made a few small changes to the copy of ReelReady on your computer so it runs on
Windows. They stay on your machine."

## 8. Check, then finish

1. Run `.venv\Scripts\python.exe scripts\doctor.py` until no `MISS` or `FAIL` lines remain. Fix one
   line at a time using the table below. `WARN` lines are fine.
2. The smoke-free check (no sample clip needed): run
   `.venv\Scripts\python.exe scripts\rr.py where --json`, then
   `.venv\Scripts\python.exe scripts\rr.py run -- ffmpeg -version`, then
   `.venv\Scripts\python.exe scripts\rr.py run -- npx --yes hyperframes --version`, then
   `.venv\Scripts\python.exe -c "from faster_whisper import WhisperModel"` (skip on ARM fallback).
   All four must work. Say plainly: "Installed and checked. A full test edit has not been run on
   Windows yet; the first real clip is the real test."
3. Go back to `SKILL.md` section B (main folder is already created; just record it) and carry on
   with the questionnaire.

## If something fails

| Symptom | Likely cause and fix |
|---|---|
| `winget` not found | Install "App Installer" from the Microsoft Store, restart the terminal |
| Tool "not found" right after install | PATH not refreshed. Restart Claude Code, re-check |
| `python3` opens the Microsoft Store | Use `py -3.12` or `.venv\Scripts\python.exe`. Do not fix the alias without asking: it is a Windows setting |
| `py -3.12` says no such version | The Python install did not finish or needs a restart. `py -0` lists versions |
| `pip install faster-whisper` fails on ARM | No CTranslate2 wheel (unverified). Use the assemblyai or elevenlabs backend (step 5) |
| `UnicodeDecodeError` or `charmap` errors | `PYTHONUTF8=1` not set in this shell. Set it, retry |
| `npx` "not recognized" or `FileNotFoundError` from Python | Patches 5 to 7 missing, or Node not on PATH yet |
| doctor says `.venv not created` though it exists | Patches 1 to 4 missing |
| doctor says `hyperframes not cached` | Run `npx --yes hyperframes --version`; if doctor still misses it, patch 9 (npm cache path) |
| HyperFrames render fails on disk or Chrome download | `FAIL free disk space`: ask the owner to free space. Chrome download blocked: check antivirus or proxy, retry |
| Whisper download warns about symlinks | A warning only. It works, just uses more disk |
| Antivirus quarantines ffmpeg or Chrome | Ask the owner to allow it; never turn protection off for them |
| File locked or "in use" in the main folder | The folder is under OneDrive. Move the main folder to `C:\AI Video Editor` |
| Anything else | Show the owner the one-line error, say what you tried, and offer WSL (plan B below) |

## Plan B: WSL2

Use it if native Windows keeps failing. Costs: a one-time `wsl --install` in an administrator
PowerShell plus a restart (about 20 minutes), a second Claude Code install inside Ubuntu, and slower
access to files on `C:` (`/mnt/c`). The owner types the commands (they need a password); you never
run sudo. One step per message, wait for "done" each time.

1. "In PowerShell run as administrator, paste `wsl --install`, restart your PC, and tell me."
2. "Ubuntu opens and asks for a new username and password. Pick anything simple and write the
   password down. Tell me when you see a prompt ending in $."
3. "In Ubuntu paste: `sudo apt update && sudo apt install -y ffmpeg git python3-venv`"
4. Node 22+ is needed too (Ubuntu's own is usually too old): see the Linux table in INSTALL.md (nvm).
5. "Install Claude Code in Ubuntu: `curl -fsSL https://claude.ai/install.sh | bash`"
6. Turn the kit's Windows path into its Ubuntu path (`C:\Users\Ana\Downloads\reelready` becomes
   `/mnt/c/Users/Ana/Downloads/reelready`). "Paste: `cd "/mnt/c/Users/<you>/.../reelready" && claude`
   and say **set up reelready** there."

Inside WSL it is plain Linux: follow `SKILL.md` as written. Main folder default so it shows on the
Windows Desktop: `/mnt/c/Users/<windows user>/Desktop/AI Video Editor` (user from
`cmd.exe /c 'echo %USERNAME%' 2>/dev/null | tr -d '\r'`). Open it with
`explorer.exe "$(wslpath -w "<path>")"`.
