#!/usr/bin/env python3
"""ReelReady sound design: voice polish, cut whooshes, hook riser + hit, caption pops, room-tone bed, music.

    python3 engines/sound.py <video> --out <mp4> [--edl edl.json] [--captions draft.words.json]
        [--preset clean|punchy|cinematic|calm] [--hook-seconds 2] [--music track.mp3] [--no-bed]

What it does
  * Voice: highpass 80 Hz -> de-esser (ffmpeg `deesser`, else a -3 dB cut at 7 kHz) -> 3:1 compressor
    at -18 dB with makeup -> (after the mix) two-pass loudnorm to -16 LUFS / -1.5 dBTP, like render_cut.
  * Cuts: from --edl (render_cut's output timeline: segment durations minus the 0.08 s crossfades), else
    ffmpeg scene detection (scene > 0.4). One whoosh per internal cut at -14 dB relative to the voice,
    placed so its transient lands on the cut: short (clean, calm), full (punchy), cinematic (cinematic).
  * Hook: punchy/cinematic get a riser that crests at --hook-seconds and an impact-bass-1 hit there;
    clean gets one click-soft at the first caption; calm gets nothing.
  * Captions (--captions: draft.words.json from render_cut, or a list of {start,end,text}): punchy adds a
    pop at -20 dB on each caption-group start (grouped like captions.py) and a sparkle on words marked
    "emphasis"/"accent": true. Never on the same moment as a whoosh or the hook hit.
  * Bed: pink room tone, lowpass 400 Hz, about -45 LUFS (29 LU under the voice) so cuts never hit
    digital silence. --no-bed turns it off.
  * Music (--music): looped/trimmed, sidechain-ducked under the voice to about -22 dB, 0.5 s fade in,
    1.5 s fade out.
  * Video is stream-copied; audio is AAC 192 kb/s at 48 kHz, +faststart.
"""
from __future__ import annotations

import argparse
import array
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True  # keep engines/ free of __pycache__
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _media import need, run, video_info  # noqa: E402
from captions import FILLERS, group, norm  # noqa: E402
from qa import loudness  # noqa: E402
from render_cut import XF  # noqa: E402

SFX = HERE / "sfx"
PRESETS = {
    # cut whoosh, hook treatment, caption pops, tail length multiplier, echo on the SFX bus
    "clean":     {"whoosh": "whoosh-short", "hook": "click", "pops": False, "tail": 1.0, "echo": False},
    "punchy":    {"whoosh": "whoosh", "hook": "riser", "pops": True, "tail": 1.0, "echo": False},
    "cinematic": {"whoosh": "whoosh-cinematic", "hook": "riser", "pops": False, "tail": 2.0, "echo": True},
    "calm":      {"whoosh": "whoosh-short", "hook": None, "pops": False, "tail": 1.0, "echo": False},
}
# Per sound: seconds kept before/after its transient (peak) and the fades on the kept window.
WINDOWS = {
    "whoosh": (0.5, 0.45, 0.0, 0.15),
    "whoosh-short": (0.12, 0.2, 0.02, 0.1),
    "whoosh-cinematic": (1.0, 0.8, 0.4, 0.5),
    "pop": (0.15, 0.35, 0.0, 0.15),
    "click-soft": (0.1, 0.25, 0.0, 0.1),
    "sparkle": (0.05, 1.0, 0.0, 0.4),
    "impact-bass-1": (0.15, 0.8, 0.0, 0.35),
    "riser": (None, 0.08, 0.4, 0.06),  # pre = hook length
}
REL = {"whoosh": -14, "hook": -14, "riser": -20, "pop": -20, "sparkle": -20, "click": -20}
BED_REL, MUSIC_GAP_REL = -29, -14
GUARD = 0.25  # no caption pop this close to a whoosh or the hook hit


def ff_json(cmd: list[str]) -> dict:
    """Run an ffmpeg command ending in loudnorm print_format=json; return the measurement."""
    p = subprocess.run(cmd, capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr, re.S)
    if p.returncode != 0 or not m:
        tail = "\n".join((p.stderr or "").strip().splitlines()[-8:])
        raise RuntimeError(f"loudness measurement failed: {tail}")
    return json.loads(m.group(0))


def lufs(j: dict) -> float:
    v = j["input_i"]
    return -70.0 if v in ("-inf", "inf") else float(v)


def momentary_max(cmd_in: list[str], af: str) -> float:
    """Loudest 400 ms (EBU momentary) of a short sound: the level a listener hears from a hit."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats"] + cmd_in +
                       ["-af", f"{af},apad=pad_dur=0.5,ebur128", "-f", "null", "-"],
                       capture_output=True, text=True)
    vals = [float(x) for x in re.findall(r"\bM:\s*(-?[\d.]+)", p.stderr)]
    return max(vals) if vals else -70.0


def peak_time(path: Path) -> float:
    """Time of the loudest 10 ms window (the transient that should land on the beat)."""
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                       capture_output=True)
    a = array.array("h", p.stdout)
    w, best, at = 80, -1.0, 0
    for i in range(0, max(len(a) - w, 1), w):
        e = sum(x * x for x in a[i:i + w])
        if e > best:
            best, at = e, i
    return at / 8000


def edl_cuts(edl: dict) -> list[float]:
    """Cut times on render_cut's output timeline (mid-point of each 0.08 s crossfade)."""
    keep = [k for k in edl["keep"] if k["end"] - k["start"] > 0.01]
    if len(keep) < 2:
        return []
    durs = [k["end"] - k["start"] for k in keep]
    xf = min(XF, min(durs) / 3)
    cuts, acc = [], durs[0]
    for d in durs[1:]:
        off = acc - xf
        cuts.append(round(off + xf / 2, 3))
        acc = off + d
    return cuts


def scene_cuts(video: str, dur: float) -> list[float]:
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", video, "-an", "-vf",
                        "select='gt(scene,0.4)',showinfo", "-f", "null", "-"], capture_output=True, text=True)
    ts = sorted(float(t) for t in re.findall(r"pts_time:\s*([\d.]+)", p.stderr))
    out: list[float] = []
    for t in ts:
        if 0.3 < t < dur - 0.3 and (not out or t - out[-1] > 0.5):
            out.append(round(t, 3))
    return out


def caption_events(path: str) -> tuple[list[float], list[float]]:
    """(caption-group starts, emphasised word starts) from draft.words.json or a {start,end,text} list."""
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict):
        data = data.get("words") or data.get("captions") or data.get("groups") or []
    items = [x for x in data if isinstance(x, dict) and "start" in x]
    if not items:
        return [], []
    emph = lambda x: bool(x.get("emphasis") or x.get("accent") or x.get("emph"))  # noqa: E731
    if "w" in items[0]:  # word list -> group exactly like captions.py
        words = [x for x in items if norm(x["w"]) not in FILLERS]
        return ([g[0]["start"] for g in group(words, 3)],
                [x["start"] for x in words if emph(x)])
    return [float(x["start"]) for x in items], [float(x["start"]) for x in items if emph(x)]


class Mix:
    """Collects SFX placements as extra ffmpeg inputs + filter chains."""

    def __init__(self, voice_lufs: float, tail: float):
        self.inputs: list[str] = []
        self.chains: list[str] = []
        self.labels: list[str] = []
        self.placed: list[dict] = []
        self.vl, self.tail = voice_lufs, tail
        self._cal: dict = {}
        self._peak: dict = {}

    def add(self, name: str, at: float, rel: float, pre: float | None = None, kind: str = "") -> None:
        """Place sound `name` so its transient sits at timeline time `at`, `rel` dB under the voice."""
        path = SFX / f"{name}.mp3"
        if not path.exists():
            raise RuntimeError(f"missing sound file engines/sfx/{path.name}")
        pk = self._peak.setdefault(name, peak_time(path))
        wpre, wpost, fi, fo = WINDOWS[name]
        wpre = pre if wpre is None else wpre
        wpost *= self.tail if name != "riser" else 1
        s0 = max(0.0, pk - wpre, pk - at)          # never start before t=0 on the timeline
        s1 = pk + wpost
        start = at - (pk - s0)
        fo = min(fo, (s1 - s0) / 2)
        af = (f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
              f"atrim=start={s0:.3f}:end={s1:.3f},asetpts=PTS-STARTPTS"
              + (f",afade=t=in:st=0:d={fi:.3f}" if fi else "")
              + f",afade=t=out:st={s1 - s0 - fo:.3f}:d={fo:.3f}")
        key = (name, round(s0, 3), round(s1, 3))
        if key not in self._cal:
            self._cal[key] = momentary_max(["-i", str(path)], af)
        gain = (self.vl + rel) - self._cal[key]
        i = len(self.inputs) // 2 + 1  # input 0 is the video; inputs holds "-i", path pairs
        self.inputs += ["-i", str(path)]
        lab = f"s{i}"
        ms = int(round(start * 1000))
        self.chains.append(f"[{i}:a]{af},volume={gain:.2f}dB,adelay=delays={ms}:all=1[{lab}]")
        self.labels.append(lab)
        self.placed.append({"sound": name, "kind": kind or name, "at": round(at, 3),
                            "starts": round(start, 3), "gain_db": round(gain, 2)})


def has_filter(name: str) -> bool:
    p = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True)
    return re.search(rf"\s{name}\s", p.stdout) is not None


def main() -> None:
    ap = argparse.ArgumentParser(description="Sound design pass: polish voice, add SFX, bed and music.")
    ap.add_argument("video")
    ap.add_argument("--out", required=True)
    ap.add_argument("--edl", default=None, help="edl.json the video was rendered from (cut times)")
    ap.add_argument("--captions", default=None, help="draft.words.json or a [{start,end,text}] list")
    ap.add_argument("--preset", default="clean", choices=list(PRESETS))
    ap.add_argument("--hook-seconds", type=float, default=None, help="default: the EDL's hook_seconds, else 2")
    ap.add_argument("--music", default=None, help="music file to loop/trim and duck under the voice")
    ap.add_argument("--no-bed", action="store_true", help="no room-tone bed")
    a = ap.parse_args()
    need("ffmpeg")
    t0 = time.time()
    if not Path(a.video).exists():
        sys.exit(f"error: video not found: {a.video}")
    if a.music and not Path(a.music).exists():
        sys.exit(f"error: music file not found: {a.music}")
    if Path(a.out).resolve() == Path(a.video).resolve():
        sys.exit("error: --out must be a new file, not the input video")
    info = video_info(a.video)
    if not info["has_audio"]:
        sys.exit("error: the video has no audio track, so there is no voice to design around")
    dur = info["duration"]
    P = PRESETS[a.preset]

    edl = json.loads(Path(a.edl).read_text()) if a.edl else None
    hook = a.hook_seconds if a.hook_seconds is not None else float((edl or {}).get("hook_seconds", 2.0))
    cuts = edl_cuts(edl) if edl else scene_cuts(a.video, dur)
    cuts = [c for c in cuts if 0.2 < c < dur - 0.2]
    groups, emph = caption_events(a.captions) if a.captions else ([], [])

    deess = "deesser=i=0.4:m=0.5:f=0.5:s=o" if has_filter("deesser") else "equalizer=f=7000:t=q:w=1.5:g=-3"
    voice = (f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,highpass=f=80,{deess},"
             f"acompressor=threshold=0.126:ratio=3:attack=8:release=150:makeup=1.5")
    try:
        vl = lufs(ff_json(["ffmpeg", "-hide_banner", "-nostats", "-i", a.video, "-vn", "-af",
                           f"{voice},loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"]))
        mix = Mix(vl, P["tail"])

        # Hook
        hook_note, hit_at = "none", None
        if P["hook"] == "riser" and dur > hook + 0.5:
            mix.add("riser", hook, REL["riser"], pre=hook, kind="hook-riser")
            mix.add("impact-bass-1", hook, REL["hook"], kind="hook-hit")
            hook_note, hit_at = "riser+hit", hook
        elif P["hook"] == "click" and groups:
            mix.add("click-soft", groups[0], REL["click"], kind="hook-click")
            hook_note, hit_at = "click", groups[0]

        # Cuts (the hook hit already marks a cut that lands on it)
        whooshes = [c for c in cuts if hit_at is None or abs(c - hit_at) > 0.35 or P["hook"] == "click"]
        for c in whooshes:
            mix.add(P["whoosh"], c, REL["whoosh"], kind="cut-whoosh")

        # Captions (punchy only), kept off the moments that already have a hit
        busy = whooshes + ([hit_at] if hit_at is not None else [])
        pops = sparkles = 0
        if P["pops"]:
            for t in emph:
                if all(abs(t - b) > GUARD for b in busy):
                    mix.add("sparkle", t, REL["sparkle"], kind="emphasis-sparkle")
                    busy.append(t); sparkles += 1
            for t in groups:
                if all(abs(t - b) > GUARD for b in busy):
                    mix.add("pop", t, REL["pop"], kind="caption-pop")
                    busy.append(t); pops += 1

        # Graph: voice + SFX bus + bed + music, summed without normalising, then loudnorm
        inputs = ["-i", a.video] + mix.inputs
        chains = mix.chains[:]
        chains.append(f"[0:a]{voice}" + ("[vx];[vx]asplit=2[v][vkey]" if a.music else "[v]"))
        layers = ["[v]"]
        if mix.labels:
            bus = "".join(f"[{x}]" for x in mix.labels)
            echo = ",aecho=0.9:0.8:110|230:0.32|0.18" if P["echo"] else ""
            chains.append(f"{bus}amix=inputs={len(mix.labels)}:normalize=0:duration=longest{echo}[sfx]"
                          if len(mix.labels) > 1 else f"{bus}anull{echo}[sfx]")
            layers.append("[sfx]")
        if not a.no_bed:
            bed_src = f"anoisesrc=d={dur:.3f}:c=pink:r=48000:a=0.5,lowpass=f=400,aformat=channel_layouts=stereo"
            bl = lufs(ff_json(["ffmpeg", "-hide_banner", "-nostats", "-f", "lavfi", "-i",
                               bed_src.replace(f"d={dur:.3f}", "d=4"), "-af",
                               "loudnorm=print_format=json", "-f", "null", "-"]))
            chains.append(f"{bed_src},volume={(vl + BED_REL) - bl:.2f}dB[bed]")
            layers.append("[bed]")
        if a.music:
            ml = lufs(ff_json(["ffmpeg", "-hide_banner", "-nostats", "-t", "60", "-i", a.music, "-vn", "-af",
                               "loudnorm=print_format=json", "-f", "null", "-"]))
            mi = len(inputs) // 2
            inputs += ["-stream_loop", "-1", "-i", a.music]
            chains.append(f"[{mi}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                          f"atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,volume={(vl + MUSIC_GAP_REL) - ml:.2f}dB[mus]")
            chains.append("[mus][vkey]sidechaincompress=threshold=0.03:ratio=3:attack=30:release=400:knee=4[mduck]")
            chains.append(f"[mduck]afade=t=in:d=0.5,afade=t=out:st={max(dur - 1.5, 0):.3f}:d=1.5[m]")
            layers.append("[m]")
        chains.append(f"{''.join(layers)}amix=inputs={len(layers)}:normalize=0:duration=first[mix]"
                      if len(layers) > 1 else "[v]anull[mix]")
        graph = ";".join(chains)

        # Pass 1: measure the mix. Pass 2: linear normalise to -16 LUFS / -1.5 dBTP (as render_cut).
        j = ff_json(["ffmpeg", "-hide_banner", "-nostats"] + inputs +
                    ["-filter_complex", f"{graph};[mix]loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json[o]",
                     "-map", "[o]", "-t", f"{dur:.3f}", "-f", "null", "-"])
        ln = "loudnorm=I=-16:TP=-1.5:LRA=11"
        if j["input_i"] not in ("-inf", "inf"):
            ln += (f":measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}"
                   f":measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true")
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        run(["ffmpeg", "-y", "-v", "error"] + inputs +
            ["-filter_complex", f"{graph};[mix]{ln},aresample=48000[o]", "-map", "0:v", "-map", "[o]",
             "-t", f"{dur:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-movflags", "+faststart", a.out])
    except RuntimeError as exc:
        sys.exit(f"error: sound pass failed: {exc}")

    meas = loudness(a.out)
    side = str(Path(a.out).with_suffix("")) + ".sound.json"
    Path(side).write_text(json.dumps({"source": a.video, "preset": a.preset, "hook_seconds": hook,
                                      "cuts": cuts, "cut_source": "edl" if edl else "scene-detect",
                                      "voice_lufs_pre": vl, "placed": mix.placed, "bed": not a.no_bed,
                                      "music": a.music, "loudness": meas}, indent=1))
    n = len(whooshes)
    extras = f", {pops} pops, {sparkles} sparkles" if P["pops"] else ""
    print(f"sound: {n} whoosh{'es' if n != 1 else ''}, hook {hook_note}{extras}, "
          f"bed {'off' if a.no_bed else 'on'}, music {'ducked' if a.music else 'none'}, preset={a.preset}, "
          f"I={meas['integrated_lufs']} LUFS TP={meas['true_peak_dbfs']} dBTP -> {a.out} "
          f"in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
