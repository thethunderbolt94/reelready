# Installing ReelReady by hand

The easy way is to drag this folder into Claude Code and say **install this**. This page is the
same thing done manually, plus troubleshooting.

## Requirements

| Piece | Why | Installed by setup |
|---|---|---|
| macOS 13+ (Apple Silicon or Intel) | primary, tested platform. Linux and Windows: see "Install by operating system" below | - |
| Homebrew | installs the tools below without sudo | you, once: https://brew.sh |
| ffmpeg / ffprobe | cutting, reframing, audio, QA | `brew install ffmpeg` |
| Node 22+ / npx | HyperFrames (captions, motion graphics; doctor on Mac still only checks 18) | `brew install node` |
| Python 3.12 + uv | repo-local `.venv` for engines | `brew install python@3.12 uv` |
| yt-dlp | watching reference links | `brew install yt-dlp` + pip in `.venv` |
| faster-whisper + Whisper `small` model (~480 MB) | free local transcription | pip in `.venv` |

Disk: about 1.7 GB for the tools (`.venv` ~480 MB, Whisper model ~480 MB, HyperFrames CLI + headless
Chrome ~680 MB), plus room to render. `doctor.py` checks free space on the temp, repo and main-folder
volumes: WARN under 3 GB, FAIL under 1.5 GB (HyperFrames itself refuses to render under 1 GB).
Nothing is installed with sudo; Python packages live in `.venv/` inside this folder.

## Steps

```bash
cd /path/to/reelready
python3 scripts/doctor.py              # what's missing (table + exit code)
bash scripts/setup.sh                  # installs what's missing; safe to re-run
python3 scripts/init.py                # creates ~/Desktop/AI Video Editor
#   or: python3 scripts/init.py --path "/Volumes/Work/AI Video Editor"
```
Then open the folder in Claude Code and say **set up reelready** for the brand questionnaire
(writes `AI Video Editor/.reelready/style-profile.json`).

`setup.sh --no-model` skips the Whisper model download (it then downloads on the first edit).

Check the engines end to end: `bash tests/smoke/run.sh` (macOS `say` makes a 20 s test clip; runs
transcribe, cut, render_cut, qa, captions; prints `SMOKE OK` or exits 1, e.g. `CAPTIONS SKIPPED: <reason>`).

## Install by operating system

Claude Code does these installs for you, on your own computer, after asking you. It never installs
anything without a yes and never uses sudo or administrator rights without telling you first.
Python packages always go in `.venv/` inside this folder. Needed everywhere: ffmpeg, Node.js 22 or
newer (HyperFrames needs it), Python 3.12, git. Disk: about 1.7 GB.

### macOS (Homebrew): the tested path

| Piece | Command Claude runs | Check it worked |
|---|---|---|
| Homebrew (once, you type your Mac password) | the line from https://brew.sh | `brew --version` |
| ffmpeg | `brew install ffmpeg` | `ffmpeg -version` |
| Node.js (22+) | `brew install node` | `node --version` |
| Python 3.12 + uv | `brew install python@3.12 uv` | `python3.12 --version` |
| git | `xcode-select --install` (usually already there) | `git --version` |
| everything else (.venv, packages, HyperFrames, Whisper model) | `bash scripts/setup.sh` | `python3 scripts/doctor.py` ends "Ready" |

### Linux (apt): best effort, not tested here

| Piece | Command Claude runs | Check it worked |
|---|---|---|
| ffmpeg, git, venv support | `sudo apt install -y ffmpeg git python3-venv` (needs your password: Claude says so first) | `ffmpeg -version` |
| Node.js 22+ | Ubuntu's own `nodejs` is usually too old. Use nvm (no sudo): install it from https://github.com/nvm-sh/nvm, then `nvm install 22` | `node --version` shows v22 or higher |
| Python 3.12 | Ubuntu 24.04 has it. Otherwise `uv` fetches it: `curl -LsSf https://astral.sh/uv/install.sh \| sh` | `uv python list` or `python3.12 --version` |
| everything else | `bash scripts/setup.sh` | `python3 scripts/doctor.py` ends "Ready" |

Fedora: same idea with `sudo dnf install ffmpeg git` (ffmpeg needs the RPM Fusion repo).

### Windows 10/11 (winget): native, not tested yet

Nothing in this kit has been run on Windows. No Windows code ships in the repo. Instead, Claude
follows [.claude/skills/reelready-setup/references/windows.md](.claude/skills/reelready-setup/references/windows.md),
which installs the tools with winget and then patches a few Mac-only spots on your copy of the kit
(local changes, never committed). Expect rough edges and report them.

| Piece | winget ID (all four found in the winget catalog; none installed on a real Windows PC by us) | Command Claude runs |
|---|---|---|
| ffmpeg | `Gyan.FFmpeg` | `winget install --id Gyan.FFmpeg -e` |
| Node.js (LTS, 22+) | `OpenJS.NodeJS.LTS` | `winget install --id OpenJS.NodeJS.LTS -e` |
| Python 3.12 | `Python.Python.3.12` | `winget install --id Python.Python.3.12 -e` |
| git | `Git.Git` | `winget install --id Git.Git -e` |

Then, from the kit folder in PowerShell:

| Step | Command | Check it worked |
|---|---|---|
| Restart Claude Code so PATH refreshes | close and reopen it | `ffmpeg -version` and `node --version` work in a new terminal |
| UTF-8 for Python | `setx PYTHONUTF8 1` (applies to new terminals) | `echo %PYTHONUTF8%` in a new cmd window prints 1 |
| Virtual environment | `py -3.12 -m venv .venv` | `.venv\Scripts\python.exe --version` |
| Python packages | `.venv\Scripts\python.exe -m pip install -r engines/requirements.txt` | `.venv\Scripts\python.exe -c "import faster_whisper"` |
| yt-dlp (optional, reference links) | `.venv\Scripts\python.exe -m pip install yt-dlp` | `.venv\Scripts\yt-dlp.exe --version` |
| HyperFrames warm-up | `npx --yes hyperframes --version` | prints a version |
| Whisper model (~480 MB, once) | `.venv\Scripts\python.exe -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"` | no error; `doctor` shows the model cached |
| Main folder | `.venv\Scripts\python.exe scripts/init.py --path "C:\AI Video Editor"` | the folder exists |

Notes for Windows:
- The Desktop is often synced by OneDrive on Windows 11, which can lock or upload big video files.
  The default main folder here is `C:\AI Video Editor`, outside OneDrive.
- Windows has no `python3` command. Use `.venv\Scripts\python.exe` (or `py -3.12` before the venv exists).
- `npx` is really `npx.cmd`. The guide patches the two places that call it by bare name.
- ARM PCs (Snapdragon): faster-whisper depends on CTranslate2, which may have no wheel for
  Windows on ARM (unverified). If `pip install` fails on it, do not fight it. Switch transcription
  to a backend the kit already has: AssemblyAI or ElevenLabs (they need a key and are paid per use,
  see "Optional keys"), and tell the owner that before choosing. x64 PCs are not affected.

### Windows plan B: WSL2

Works, and the kit runs unchanged inside it as plain Linux, but the costs are real: a one-time
`wsl --install` from an administrator PowerShell and a restart, about 20 minutes, a second copy of
Claude Code inside Ubuntu, clips must sit in the Linux side or `/mnt/c/...` (slower), and Windows
apps cannot open files as easily. Steps: `wsl --install`, restart, open Ubuntu, follow the Linux table
above, then `cd` to the kit and run `claude` there.

## Optional keys

Say "set up reelready" and choose AssemblyAI or ElevenLabs at the transcription question, or:
```bash
printf '%s' 'YOUR_KEY' | python3 scripts/rr.py set-key assemblyai     # or elevenlabs
```
The key goes to `<main folder>/.reelready/.env` (mode 600). It is never written into this repo.

## Where things live

| Path | What |
|---|---|
| `.reelready/home.json` (repo, gitignored) | which folder is your main folder |
| `<main>/.reelready/style-profile.json` | your brand profile |
| `<main>/.reelready/.env` | optional API keys |
| `<main>/.reelready/work/` | scratch: transcripts, proxies, intermediate renders |
| `<main>/exports/<date>-<slug>/` | finished videos |

Override the main folder for one session with `REELREADY_HOME=/path`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| doctor: `hyperframes not cached` | `npx --yes hyperframes --version` |
| Windows: command "not found" right after installing | Restart Claude Code (or open a new terminal) so PATH refreshes |
| Windows: `python3` opens the Microsoft Store | Use `.venv\Scripts\python.exe`, or turn off the python3 "app execution alias" in Windows settings |
| doctor: `FAIL free disk space` / "disk is almost full" | Free space (Trash, old videos, `<main>/.reelready/work/`); renders need 1.5 GB+, 3 GB+ is comfortable |
| doctor: `.venv not created` | `brew install uv` then `bash scripts/setup.sh` |
| faster-whisper fails to install | Python too new for its wheels; setup pins 3.12 via uv. Delete `.venv` and re-run setup |
| Reference link "login required" | Instagram/TikTok sometimes block downloads. Save the video and drop it in `references/` |
| Captions misspell your business name | It's in your profile; Claude corrects only that and lists the fix in `plan.md` |
| Video is sideways | Phone rotation metadata; Claude reads it during probe. Re-run the edit and mention it |

## Uninstall

Delete this folder. Optionally delete `~/Desktop/AI Video Editor` (your videos) and the Whisper
model in `~/.cache/huggingface/hub/models--Systran--faster-whisper-small`.
