#!/usr/bin/env python3
"""Create the ReelReady folder contract (idempotent). Stdlib only.

  python3 scripts/init.py                       # ~/Desktop/AI Video Editor
  python3 scripts/init.py --path "/some/where"  # custom location (folder is created if missing)
  python3 scripts/init.py --path X --no-pointer # don't remember X as the main folder (tests)

Never deletes or overwrites user files. Prints a JSON summary.
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
POINTER = REPO / ".reelready" / "home.json"


def brand():
    try:
        b = json.loads((REPO / "reelready.config.json").read_text())["brand"]
        return f'{b["name"]} by {b["by"]}'
    except Exception:
        return "ReelReady"


READMES = {
    "raw footage": """RAW FOOTAGE - drop your phone clips here.

- Any video file works: .mov, .mp4 straight off your phone is perfect.
- Talking-to-camera clips and b-roll (shots of your product, space, hands) both go here.
- {brand} only READS this folder. Your originals are never changed or deleted.

Then tell Claude: "edit this" (or "edit the newest clip").
""",
    "references": """REFERENCES - videos you love the look of.

- Put example videos or screenshots here, or paste links (one per line) into links.txt.
- Claude studies these for pacing, captions and colour. It copies the feel, never the content.
- Read-only for {brand}.
""",
    "assets": """ASSETS - your brand kit.

- logo.png        (transparent background is best)
- fonts/          (.ttf or .otf files, optional - good defaults are used otherwise)
- music/          (tracks you own or have a licence for, optional)
- sfx/            (whooshes, pops, optional)
- Read-only for {brand}: it uses these, it never changes them.
""",
    "exports": """EXPORTS - finished videos land here.

Each edit gets its own folder, e.g. 2026-10-28-latte-art/
  final.mp4    the finished video, ready to post
  draft.mp4    the clean cut before captions and graphics
  plan.md      the edit plan you approved
  edl.json     the cut list (technical)
  caption.txt  a DRAFT post caption, only if you asked for one. Read it before posting.

This is the only folder {brand} writes into.
""",
}


def write_if_missing(path: Path, text: str, created: list):
    if not path.exists():
        path.write_text(text)
        created.append(str(path))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--path", default=str(Path.home() / "Desktop" / "AI Video Editor"),
                    help='main folder to create (default: ~/Desktop/AI Video Editor)')
    ap.add_argument("--no-pointer", action="store_true", help="do not record this folder as the main folder")
    a = ap.parse_args()

    home = Path(a.path).expanduser().resolve()
    name = brand()
    created = []
    try:
        for d in ["raw footage", "references", "assets", "assets/fonts", "assets/music", "assets/sfx",
                  "exports", ".reelready", ".reelready/work"]:
            p = home / d
            if not p.exists():
                p.mkdir(parents=True)
                created.append(str(p))
        for folder, text in READMES.items():
            write_if_missing(home / folder / "README.txt", text.format(brand=name), created)
        write_if_missing(home / "references" / "links.txt",
                         "# One link per line: Instagram, TikTok or YouTube videos whose look you like.\n", created)
        write_if_missing(home / ".reelready" / "README.txt",
                         f"{name} internal folder: your style profile, private keys (.env) and scratch work.\n"
                         "Safe to ignore. Do not share the .env file - it holds your API keys if you added any.\n",
                         created)
    except PermissionError as e:
        print(json.dumps({"ok": False, "error": f"permission denied: {e.filename}"}))
        sys.exit(1)

    if not a.no_pointer:
        POINTER.parent.mkdir(parents=True, exist_ok=True)
        POINTER.write_text(json.dumps({"main_folder": str(home),
                                       "set_at": dt.datetime.now().isoformat(timespec="seconds")}, indent=2) + "\n")

    print(json.dumps({
        "ok": True,
        "main_folder": str(home),
        "created": created,
        "already_there": not created,
        "pointer": None if a.no_pointer else str(POINTER),
        "profile_exists": (home / ".reelready" / "style-profile.json").exists(),
    }, indent=2))


if __name__ == "__main__":
    main()
