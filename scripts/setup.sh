#!/usr/bin/env bash
# ReelReady installer. Idempotent: safe to run again and again. Never uses sudo.
#   bash scripts/setup.sh            install whatever is missing, then print a summary
#   bash scripts/setup.sh --no-model skip the one-time Whisper model download (~480 MB)
# macOS first (Homebrew). Linux best-effort. Windows: prints instructions and exits.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$REPO/.venv"
PY="$VENV/bin/python"
WHISPER_MODEL="small"
GET_MODEL=1
for arg in "$@"; do
  case "$arg" in
    --no-model) GET_MODEL=0 ;;
    -h|--help) sed -n '2,5p' "$0"; exit 0 ;;
  esac
done

BRAND="$(python3 -c 'import json,sys;b=json.load(open(sys.argv[1]))["brand"];print(b["name"]+" by "+b["by"])' "$REPO/reelready.config.json" 2>/dev/null || echo ReelReady)"
DONE=(); SKIP=(); FAIL=(); TODO=()
say()  { printf '\n==> %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

say "$BRAND setup"
OS="$(uname -s 2>/dev/null || echo unknown)"

case "$OS" in
  MINGW*|MSYS*|CYGWIN*|Windows_NT)
    cat <<'WIN'
Windows is not supported natively yet. The easy path:
  1. Install WSL2 (Ubuntu) from the Microsoft Store: open PowerShell and run  wsl --install
  2. Open the Ubuntu app, install the basics:  sudo apt update && sudo apt install -y ffmpeg nodejs npm python3-venv
  3. Put this folder inside Ubuntu (e.g. ~/reelready) and run:  bash scripts/setup.sh
  4. Point Claude Code at that folder and say: set up reelready
WIN
    exit 0 ;;
esac

# ---------------------------------------------------------------- system tools
if [ "$OS" = "Darwin" ]; then
  if ! have brew && [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"; fi
  if ! have brew && [ -x /usr/local/bin/brew ]; then eval "$(/usr/local/bin/brew shellenv)"; fi
  if have brew; then
    for pkg in ffmpeg node python@3.12 uv yt-dlp; do
      if brew list --formula "$pkg" >/dev/null 2>&1; then SKIP+=("$pkg (already installed)")
      else
        say "Installing $pkg (Homebrew)"
        if brew install "$pkg"; then DONE+=("$pkg"); else FAIL+=("$pkg (brew install $pkg)"); fi
      fi
    done
  else
    TODO+=("Install Homebrew: open Terminal, paste the line from https://brew.sh, enter your Mac password, then run setup again")
    for b in ffmpeg node; do have "$b" || FAIL+=("$b (needs Homebrew)"); done
  fi
else
  # Linux / other unix: use Homebrew if present, otherwise tell the user what to install.
  if have brew; then
    for pkg in ffmpeg node uv yt-dlp; do
      have "${pkg%%@*}" && SKIP+=("$pkg (already installed)") && continue
      if brew install "$pkg"; then DONE+=("$pkg"); else FAIL+=("$pkg"); fi
    done
  else
    MISSING=()
    have ffmpeg || MISSING+=(ffmpeg)
    have node   || MISSING+=(nodejs npm)
    have python3 || MISSING+=(python3)
    python3 -c 'import venv, ensurepip' >/dev/null 2>&1 || MISSING+=(python3-venv)
    if [ ${#MISSING[@]} -gt 0 ]; then
      TODO+=("Install system packages (needs your password, run it yourself): sudo apt install -y ${MISSING[*]}   (Fedora: sudo dnf install ${MISSING[*]})")
    fi
    have uv || TODO+=("Optional, faster installs: curl -LsSf https://astral.sh/uv/install.sh | sh")
  fi
fi

# ---------------------------------------------------------------- repo-local python
venv_ok() { [ -x "$PY" ] && "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; }
if venv_ok; then
  SKIP+=(".venv ($("$PY" --version 2>&1))")
else
  say "Creating repo-local Python environment (.venv)"
  rm -rf "$VENV" 2>/dev/null
  if have uv && uv venv --python 3.12 "$VENV" >/dev/null 2>&1; then DONE+=(".venv via uv (Python 3.12)")
  else
    PYBIN=""
    for c in python3.12 python3.11 python3.13 python3.10 python3; do
      if have "$c" && "$c" -c 'import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)' 2>/dev/null; then PYBIN="$c"; break; fi
    done
    if [ -n "$PYBIN" ] && "$PYBIN" -m venv "$VENV"; then DONE+=(".venv via $PYBIN")
    else FAIL+=(".venv (need Python 3.10-3.13: brew install python@3.12 or uv)"); fi
  fi
fi

if venv_ok; then
  say "Installing Python packages into .venv (faster-whisper, yt-dlp, engine requirements)"
  REQS=(-U faster-whisper yt-dlp)
  [ -f "$REPO/engines/requirements.txt" ] && REQS+=(-r "$REPO/engines/requirements.txt")
  if have uv; then uv pip install --quiet --python "$PY" "${REQS[@]}"; RC=$?
  else "$PY" -m pip install --quiet --upgrade pip >/dev/null 2>&1; "$PY" -m pip install --quiet "${REQS[@]}"; RC=$?; fi
  if [ $RC -eq 0 ]; then DONE+=("python packages"); else FAIL+=("python packages (see errors above)"); fi
  [ -f "$REPO/engines/requirements.txt" ] || TODO+=("engines/requirements.txt not found: re-download the kit if editing fails")
fi

# ---------------------------------------------------------------- HyperFrames warm-up
if have npx; then
  say "Warming up HyperFrames (captions + motion graphics). First run downloads it once."
  if (cd "$REPO" && npx --yes hyperframes --version); then DONE+=("hyperframes"); else FAIL+=("hyperframes (npx --yes hyperframes --version)"); fi
else
  FAIL+=("hyperframes (needs node + npx)")
fi

# ---------------------------------------------------------------- Whisper model (one time)
if [ $GET_MODEL -eq 1 ] && venv_ok && "$PY" -c 'import faster_whisper' >/dev/null 2>&1; then
  if [ -d "${HF_HOME:-$HOME/.cache/huggingface}/hub/models--Systran--faster-whisper-$WHISPER_MODEL" ]; then
    SKIP+=("whisper model '$WHISPER_MODEL' (cached)")
  else
    say "Downloading the free local transcription model ($WHISPER_MODEL, ~480 MB, one time only)"
    if "$PY" -c "from faster_whisper import WhisperModel; WhisperModel('$WHISPER_MODEL', device='cpu', compute_type='int8')"; then
      DONE+=("whisper model '$WHISPER_MODEL'")
    else FAIL+=("whisper model (will retry on first edit)"); fi
  fi
fi

# ---------------------------------------------------------------- summary
say "Summary"
for x in "${DONE[@]+"${DONE[@]}"}"; do echo "  installed  $x"; done
for x in "${SKIP[@]+"${SKIP[@]}"}"; do echo "  ok         $x"; done
for x in "${FAIL[@]+"${FAIL[@]}"}"; do echo "  FAILED     $x"; done
for x in "${TODO[@]+"${TODO[@]}"}"; do echo "  YOU DO     $x"; done
echo
python3 "$REPO/scripts/doctor.py" --fast
exit $?
