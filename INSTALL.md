# Installing ReelReady by hand

The easy way is to drag this folder into Claude Code and say **install this**. This page is the
same thing done manually, plus troubleshooting.

## Requirements

| Piece | Why | Installed by setup |
|---|---|---|
| macOS 13+ (Apple Silicon or Intel) | primary platform | - |
| Homebrew | installs the tools below without sudo | you, once: https://brew.sh |
| ffmpeg / ffprobe | cutting, reframing, audio, QA | `brew install ffmpeg` |
| Node 18+ / npx | HyperFrames (captions, motion graphics) | `brew install node` |
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

## Linux (best effort)

Install system packages yourself (needs your password):
```bash
sudo apt install -y ffmpeg nodejs npm python3-venv     # Debian/Ubuntu
```
Optional: uv (`curl -LsSf https://astral.sh/uv/install.sh | sh`). Then `bash scripts/setup.sh`.

## Windows

Use WSL2: `wsl --install` in PowerShell, open Ubuntu, follow the Linux steps, then point Claude
Code at the folder inside WSL.

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
| doctor: `FAIL free disk space` / "disk is almost full" | Free space (Trash, old videos, `<main>/.reelready/work/`); renders need 1.5 GB+, 3 GB+ is comfortable |
| doctor: `.venv not created` | `brew install uv` then `bash scripts/setup.sh` |
| faster-whisper fails to install | Python too new for its wheels; setup pins 3.12 via uv. Delete `.venv` and re-run setup |
| Reference link "login required" | Instagram/TikTok sometimes block downloads. Save the video and drop it in `references/` |
| Captions misspell your business name | It's in your profile; Claude corrects only that and lists the fix in `plan.md` |
| Video is sideways | Phone rotation metadata; Claude reads it during probe. Re-run the edit and mention it |

## Uninstall

Delete this folder. Optionally delete `~/Desktop/AI Video Editor` (your videos) and the Whisper
model in `~/.cache/huggingface/hub/models--Systran--faster-whisper-small`.
