#!/usr/bin/env python3
"""
Cut YouTube Shorts from Fabric wisdom files and (optionally) smart-reframe to vertical 9:16.

- Auto-selects the correct MP4 for the latest Sunday and service (1st/2nd) using your time rules
- Parses '# VIDEO CLIP SUGGESTIONS:' from wisdom files
- Cuts clips with ffmpeg (reliable re-encode or fast copy)
- Optional: --vertical-smart to run smart_reframe_vertical.py on each output (speaker-centered vertical)
"""

import argparse, datetime, os, re, subprocess, sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# ---------- Defaults matching your setup ----------
DEFAULT_BASE_DIR = "/home/william/CAG Dropbox/Media/Sermon Recordigs"
DEFAULT_SEND_MAIL = "/home/william/scripts/PERSONAL/sunday-wisdom/gather_wisdom"
DEFAULT_TMP = f"{DEFAULT_SEND_MAIL}/tmp"
DEFAULT_FFMPEG = "/usr/bin/ffmpeg"

# Accepts mm:ss or hh:mm:ss (e.g., 22:12 or 1:02:03)
TIME_RE = re.compile(r'^(?:(\d+):)?([0-5]?\d):([0-5]?\d)$')

# Header section: “# VIDEO CLIP SUGGESTIONS” with optional colon
SUGGESTION_SECTION_RE = re.compile(
    r"""
    ^\s*\#\s*VIDEO\W*CLIP\W*SUGGESTIONS\s*:?\s*$   # header line, colon optional
    (.*?)                                          # capture section body (non-greedy)
    (?=^\s*\#\s|\Z)                                # until next header or EOF
    """,
    flags=re.IGNORECASE | re.MULTILINE | re.DOTALL | re.VERBOSE
)

# Each numbered suggestion block (Seconds line optional; Start/End required)
BLOCK_RE = re.compile(
    r"""
    ^\s*\d+\.\s*(?:\*\*.*?\*\*)?.*$                 # "1. **(45 Seconds)**"  (optional)
    .*?^\s*\*\*Start:\*\*\s*([0-9:\s]+?)\s*$        # Start: 13:06
    .*?^\s*\*\*End:\*\*\s*([0-9:\s]+?)\s*$          # End:   13:51
    (?:.*?^\s*\*\*First\s+Sentence:\*\*\s*"(.*?)"\s*$)?  # optional
    (?:.*?^\s*\*\*Last\s+Sentence:\*\*\s*"(.*?)"\s*$)?   # optional
    """,
    flags=re.MULTILINE | re.DOTALL | re.VERBOSE
)

# ---------- Helpers ----------
def parse_ts(ts: str) -> float:
    """
    Parse time strings like '22:12' or '1:02:03' into seconds.
    Also tolerates stray quotes/spaces and leading/trailing text.
    """
    ts = str(ts).strip().strip('"').strip("'")
    # Sometimes the value comes with extra spacing or punctuation; keep only digits and colons.
    ts = re.sub(r'[^0-9:]', '', ts)

    m = TIME_RE.match(ts)
    if not m:
        # As a fallback, try to interpret a raw number as seconds
        if ts.isdigit():
            return float(ts)
        raise ValueError(f"Unrecognized time format: {ts!r}")

    h = int(m.group(1) or 0)
    mi = int(m.group(2))
    s = int(m.group(3))
    return h * 3600 + mi * 60 + s

def slug(s: str, max_len: int = 60) -> str:
    s = s.strip().lower()
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_"):
            out.append("-")
    cleaned = re.sub(r"-+", "-", "".join(out)).strip("-")
    return cleaned[:max_len] or "clip"

def run(cmd: List[str], dry_run: bool = False, check: bool = False) -> int:
    print("▶", " ".join(cmd))
    if dry_run:
        return 0
    proc = subprocess.run(cmd, check=check)
    return proc.returncode

def last_sunday_date() -> str:
    today = datetime.date.today()
    offset = (today.weekday() + 1) % 7  # Monday=0 ... Sunday=6 => if Sunday => 0
    return (today - datetime.timedelta(days=offset)).strftime("%Y-%m-%d")

def parse_filename_time(fname: str) -> Optional[Tuple[int, int]]:
    """
    Expect 'YYYY-MM-DD HH-MM-SS.mp4'. Return (hour, minute) or None.
    """
    try:
        parts = fname.split(" ")
        if len(parts) < 2:
            return None
        time_part = parts[1].split(".")[0]  # HH-MM-SS
        hh, mm, _ = time_part.split("-")
        return (int(hh), int(mm))
    except Exception:
        return None

def minutes_after_midnight(h: int, m: int) -> int:
    return h * 60 + m

def pick_video_for_service(base_dir: Path, sunday_str: str, service: str) -> Optional[Path]:
    """
    Find the appropriate MP4 in base_dir for the given Sunday + service rules.
    - Filenames must start with 'YYYY-MM-DD '
    - Window: 09:00–13:00
    - 1st service: < 11:00
    - 2nd service: >= 11:15
    Choose first match in sorted order.
    """

    # Support multiple video file extensions
    exts = [".mp4", ".mkv", ".mov", ".webm"]
    candidates = []
    for ext in exts:
        candidates.extend(sorted(base_dir.glob(f"{sunday_str}*{ext}")))
    if not candidates:
        return None

    for p in candidates:
        t = parse_filename_time(p.name)
        if not t:
            continue
        hh, mm = t
        total = minutes_after_midnight(hh, mm)
        if total < 540 or total > 780:
            continue
        if service == "1st" and total < 660:      # < 11:00
            return p
        if service == "2nd" and total >= 675:     # >= 11:15
            return p
    return None

def extract_suggestions(md_text: str) -> List[Dict]:
    m = SUGGESTION_SECTION_RE.search(md_text)
    if not m:
        return []
    section = m.group(1)

    clips = []
    for b in BLOCK_RE.finditer(section):
        start_raw = (b.group(1) or "").strip()
        end_raw = (b.group(2) or "").strip()
        first_sentence = (b.group(3) or "").strip()

        try:
            start_s = parse_ts(start_raw)
            end_s = parse_ts(end_raw)
        except Exception as e:
            print(f"⚠️  Skipping block due to time parse error: {e}")
            continue
        if end_s <= start_s:
            print(f"⚠️  Skipping invalid range {start_raw}–{end_raw} (end <= start)")
            continue
        clips.append(
            {
                "start_s": start_s,
                "end_s": end_s,
                "start_raw": start_raw,
                "end_raw": end_raw,
                "first_sentence": first_sentence,
            }
        )
    return clips

def build_out_name(i: int, start_raw: str, end_raw: str, first_sentence: str, use_sentence: bool, prefix: str):
    if use_sentence and first_sentence:
        return f"{prefix}{i:02d}_{slug(first_sentence)}.mp4"
    return f"{prefix}{i:02d}_{start_raw.replace(':','-')}_{end_raw.replace(':','-')}.mp4"

def make_clip(
    ffmpeg_bin: str,
    input_mp4: Path,
    start_s: float,
    end_s: float,
    out_path: Path,
    fast_copy: bool,
    fps: int,
    crf: int,
    preset: str,
    dry_run: bool,
):
    duration = end_s - start_s
    cmd = [ffmpeg_bin, "-y", "-ss", f"{start_s:.3f}", "-i", str(input_mp4), "-t", f"{duration:.3f}"]

    if fast_copy:
        # Stream copy: fast, but cuts at nearest keyframe
        cmd += ["-c", "copy", str(out_path)]
    else:
        # Re-encode for accurate cutting
        cmd += [
            "-r", str(fps), "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out_path)
        ]

    rc = run(cmd, dry_run=dry_run)
    if rc != 0:
        print(f"❌ ffmpeg failed for: {out_path.name}")
    else:
        print(f"✅ Wrote: {out_path.name}")

# ---------- Main ----------
def main():
    ap = argparse.ArgumentParser(
        description="Create clips from Fabric’s 'VIDEO CLIP SUGGESTIONS' using the right Sunday MP4 automatically."
    )
    # Which inputs
    ap.add_argument("--service", choices=["1st", "2nd"], required=False,
                    help="Service selector. If omitted: auto-pick 1st then 2nd.")
    ap.add_argument("--wisdom-file",
                    help="Path to wisdom file. Default: <SEND_MAIL>/tmp/{1st|2nd}_service_wisdom.txt")
    ap.add_argument("--base-dir", default=DEFAULT_BASE_DIR, help="Folder with source MP4s")
    ap.add_argument("--sunday", default=None, help="Force Sunday date (YYYY-MM-DD). Default: last Sunday")

    # Output and ffmpeg
    ap.add_argument("--outdir", default="shorts", help="Output directory (default: ./shorts)")
    ap.add_argument("--ffmpeg", default=DEFAULT_FFMPEG, help="Path to ffmpeg")
    ap.add_argument("--use-sentence-name", action="store_true",
                    help="Name clips from the first sentence")
    ap.add_argument("--fast-copy", action="store_true",
                    help="Use stream copy for faster cuts (keyframe-aligned). Omit for precise re-encode.")
    ap.add_argument("--fps", type=int, default=30, help="Output FPS when re-encoding (default 30)")
    ap.add_argument("--crf", type=int, default=23, help="x264 CRF (default 23)")
    ap.add_argument("--preset", default="veryfast", help="x264 preset (default veryfast)")
    ap.add_argument("--dry-run", action="store_true", help="Print commands only")

# Smart vertical reframing (speaker-centered)
    ap.add_argument("--vertical-smart", action="store_true", dest="vertical_smart",
                help="Run smart_reframe_vertical.py on each clip to produce 9:16 speaker-centered output.")
    ap.add_argument("--smart-script", default="/home/william/scripts/PERSONAL/sunday-wisdom/shorts_maker/smart_reframe_vertical.py",
                    help="Path to smart_reframe_vertical.py")
    ap.add_argument("--smart-stride", type=int, default=5,
                    help="Detect every Nth frame for smart reframing (default 5). Lower = more accurate.")
    ap.add_argument("--smart-smooth", type=float, default=0.85,
                    help="EMA smoothing factor for smart reframing (default 0.85).")
    ap.add_argument("--smart-debug-overlay", action="store_true",
                    help="Draw crop/center on original in debug SxS.")
    ap.add_argument("--smart-debug-sbs", action="store_true",
                    help="Write side-by-side debug video (<output>_debug.mp4).")
    ap.add_argument("--smart-export-csv", action="store_true",
                    help="Export per-frame positions to CSV (<output>.csv).")


    ap.add_argument(
        "--max-clips",
        type=int,
        default=None,
        help="Maximum number of clips to generate (default: unlimited)"
    )

    args = ap.parse_args()

    base_dir = Path(args.base_dir)
    if not base_dir.exists():
        print(f"❌ Base dir not found: {base_dir}")
        sys.exit(1)

    sunday = args.sunday or last_sunday_date()
    print(f"📅 Sunday: {sunday}")

    # Resolve service & wisdom file
    wisdom_file: Optional[Path] = Path(args.wisdom_file) if args.wisdom_file else None
    service: Optional[str] = args.service

    if not wisdom_file:
        tmp_dir = Path(DEFAULT_TMP)
        if service == "1st":
            wisdom_file = tmp_dir / "1st_service_wisdom.txt"
        elif service == "2nd":
            wisdom_file = tmp_dir / "2nd_service_wisdom.txt"
        else:
            # Auto: try 1st then 2nd
            wf1 = tmp_dir / "1st_service_wisdom.txt"
            wf2 = tmp_dir / "2nd_service_wisdom.txt"
            wisdom_file = wf1 if wf1.exists() else (wf2 if wf2.exists() else None)
            service = "1st" if wisdom_file == wf1 else ("2nd" if wisdom_file == wf2 else None)

    if not wisdom_file or not wisdom_file.exists():
        print("❌ Could not locate a wisdom file. Use --wisdom-file or ensure tmp files exist.")
        sys.exit(2)

    print(f"📝 Using wisdom file: {wisdom_file}")
    print(f"🕍 Service: {service or 'auto'}")

    # Find MP4 based on Sunday+service
    input_mp4: Optional[Path] = None
    if service:
        input_mp4 = pick_video_for_service(base_dir, sunday, service)
    else:
        input_mp4 = pick_video_for_service(base_dir, sunday, "1st") or \
                    pick_video_for_service(base_dir, sunday, "2nd")

    if not input_mp4 or not input_mp4.exists():
        print("❌ Could not find a matching MP4 for that Sunday/service in the base directory.")
        sys.exit(3)

    print(f"🎬 Input MP4: {input_mp4}")

    # Parse suggestions
    wisdom_text = wisdom_file.read_text(encoding="utf-8", errors="ignore")

    clips = extract_suggestions(wisdom_text)
    if not clips:
        print("❌ No parsable 'VIDEO CLIP SUGGESTIONS' found in the wisdom file.")
        sys.exit(4)

    if args.max_clips is not None:
        clips = clips[:args.max_clips]
        print(f"🔢 Limiting to {len(clips)} clips (max-clips={args.max_clips})")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"📁 Output dir: {outdir}")
    print(f"⚙️ Cut mode: {'fast-copy (keyframe aligned)' if args.fast_copy else 're-encode (accurate)'}")
    if args.vertical_smart:
        print("🤖 Smart vertical reframing: ENABLED")


    # Process all suggestions
    for i, c in enumerate(clips, start=1):
        out_name = build_out_name(
            i, c["start_raw"], c["end_raw"], c["first_sentence"], args.use_sentence_name, prefix=""
        )
        out_path = outdir / out_name

        # 1) Cut clip
        make_clip(
            ffmpeg_bin=args.ffmpeg,
            input_mp4=input_mp4,
            start_s=c["start_s"],
            end_s=c["end_s"],
            out_path=out_path,
            fast_copy=args.fast_copy,
            fps=args.fps,
            crf=args.crf,
            preset=args.preset,
            dry_run=args.dry_run,
        )

        # 2) Optional smart vertical reframing
        if args.vertical_smart:
            vertical_out = out_path.with_name(out_path.stem + "_vertical" + out_path.suffix)
            cmd = [
                "python3", args.smart_script,
                "-i", str(out_path),
                "-o", str(vertical_out),
                "--stride", str(args.smart_stride),
                "--smooth", str(args.smart_smooth),
            ]
            if args.smart_debug_overlay:
                cmd.append("--debug-overlay")
            if args.smart_debug_sbs:
                cmd.append("--debug-sbs")
            if args.smart_export_csv:
                cmd.append("--export-csv")

            print(f"🤖 Reframing vertically → {vertical_out.name}")
            rc = run(cmd, dry_run=args.dry_run)
            if rc != 0:
                print(f"❌ smart_reframe_vertical failed for {vertical_out.name}")

    print("✅ All suggestions processed.")

if __name__ == "__main__":
    main()
