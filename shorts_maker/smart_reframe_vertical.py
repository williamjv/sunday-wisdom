#!/usr/bin/env python3
"""
Smart vertical reframing for speaker-centric Shorts (OpenCV + ffmpeg, MoviePy-free).

- Detects a (largest) face using OpenCV Haar cascade at a configurable stride
- EMA-smooths the horizontal center to avoid jitter
- Crops a moving 9:16 window; outputs 1080x1920
- Letterbox option (--letterbox <0..1>) to add bars (show more head/foot room)
- Letterbox alignment (--letterbox-align top|center|bottom). 'top' = bar only at bottom.
- Writes the vertical video with OpenCV
- Muxes the original audio back in using ffmpeg
- Optional: side-by-side (original | vertical) debug video via OpenCV
- Optional: export CSV of positions
"""

import argparse
import csv
import os
import shlex
import subprocess
from pathlib import Path

import numpy as np
import cv2


def parse_args():
    ap = argparse.ArgumentParser(description="Auto-center speaker and reframe to vertical 9:16 (1080x1920).")
    ap.add_argument("-i", "--input", required=True, help="Input video (landscape)")
    ap.add_argument("-o", "--output", required=True, help="Output vertical video (mp4)")
    ap.add_argument("--stride", type=int, default=4, help="Detect every Nth frame (default 4)")
    ap.add_argument("--smooth", type=float, default=0.92, help="EMA smoothing factor (0..1). Higher = steadier.")
    ap.add_argument("--min-face", type=int, default=80, help="Minimum face width for detection (px)")
    ap.add_argument("--fps", type=float, default=None, help="Override output FPS (default: source)")

    # Stability / stickiness knobs
    ap.add_argument("--stick-frames", type=int, default=35,
                    help="Min detection steps to stick before considering a target switch.")
    ap.add_argument("--switch-area-ratio", type=float, default=2.0,
                    help="New face must be this many times larger (area) to force a switch.")
    ap.add_argument("--max-px-jump", type=int, default=30,
                    help="Maximum x-center change allowed per detection step.")
    ap.add_argument("--no-prefer-near-prev", action="store_true",
                    help="Disable proximity preference when choosing faces (not recommended).")

    # Letterbox (show more around speaker)
    ap.add_argument("--letterbox", type=float, default=1.0,
                    help="Scale vertical content inside 1080x1920 canvas (0.5..1.0). "
                         "e.g., 0.92 adds padding and shows more head/foot room.")
    ap.add_argument("--letterbox-align", choices=["top", "center", "bottom"], default="top",
                    help="Vertical alignment of the letterboxed content inside the 1080x1920 canvas. "
                         "'top' places content at top (padding only at bottom).")

    # Debug & CSV
    ap.add_argument("--debug-overlay", action="store_true",
                    help="Draw crop window & smoothed center on original frames (for SxS output).")
    ap.add_argument("--debug-sbs", action="store_true",
                    help="Write side-by-side debug video: <output>_debug.mp4 (Original|Vertical).")
    ap.add_argument("--export-csv", action="store_true",
                    help="Export per-frame positions to CSV: <output>.csv")

    # (Used only if a re-encode becomes necessary during muxing.)
    ap.add_argument("--crf", type=int, default=23, help="CRF for fallback re-encode during audio mux (rare).")
    return ap.parse_args()


def detect_xcenters(
    video_path: Path,
    stride: int,
    min_face_w: int,
    *,
    stick_frames: int = 15,
    switch_area_ratio: float = 1.5,
    max_px_jump: int = 60,
    prefer_near_prev: bool = True,
):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)
    if face_cascade.empty():
        raise RuntimeError(f"Failed to load Haar cascade from {cascade_path}")

    xcenters_raw = []
    frame_idx = 0

    # Target tracking state
    target_xc = W / 2.0
    target_area = 1.0
    frames_since_switch = 10**9

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if stride <= 1 or frame_idx % stride == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(min_face_w, min_face_w)
            )

            if len(faces) > 0:
                # Score faces with area and proximity to previous target
                candidates = []
                for (x, y, w, h) in faces:
                    area = float(w) * float(h)
                    xc = x + w / 2.0
                    dist = abs(xc - target_xc)
                    score = (area - dist) if prefer_near_prev else area
                    candidates.append((score, xc, area))

                candidates.sort(reverse=True, key=lambda t: t[0])
                _, best_xc, best_area = candidates[0]

                should_switch = False
                if frames_since_switch >= stick_frames:
                    if best_area >= switch_area_ratio * target_area:
                        should_switch = True
                    else:
                        if prefer_near_prev and abs(best_xc - target_xc) < (W * 0.15):
                            if best_area > target_area * 1.1:
                                should_switch = True

                if should_switch:
                    target_xc = best_xc
                    target_area = max(1.0, best_area)
                    frames_since_switch = 0
                else:
                    delta = best_xc - target_xc
                    if abs(delta) > max_px_jump:
                        delta = np.sign(delta) * max_px_jump
                    target_xc = target_xc + delta
                    target_area = 0.9 * target_area + 0.1 * max(1.0, best_area)
                    frames_since_switch += 1

        xcenters_raw.append(target_xc)
        frame_idx += 1

    duration_frames = len(xcenters_raw)
    cap.release()
    return xcenters_raw, W, H, fps, duration_frames


def ema_smooth(data, alpha: float) -> np.ndarray:
    if not data:
        return np.array([])
    out = np.zeros(len(data), dtype=np.float32)
    out[0] = data[0]
    for i in range(1, len(data)):
        out[i] = alpha * out[i-1] + (1 - alpha) * data[i]
    return out


def mux_audio(ffmpeg_bin: str, src_video: Path, orig_video: Path, tmp_audio: Path):
    # Extract audio to AAC (M4A)
    cmd_extract = f'{ffmpeg_bin} -y -i {shlex.quote(str(orig_video))} -vn -acodec aac -b:a 160k {shlex.quote(str(tmp_audio))}'
    subprocess.run(cmd_extract, shell=True, check=True)
    # Mux: copy video stream, re-encode/streamcopy audio as needed
    tmp_muxed = src_video.with_suffix(".withaudio.mp4")
    cmd_mux = f'{ffmpeg_bin} -y -i {shlex.quote(str(src_video))} -i {shlex.quote(str(tmp_audio))} ' \
              f'-c:v copy -c:a aac -shortest {shlex.quote(str(tmp_muxed))}'
    subprocess.run(cmd_mux, shell=True, check=True)
    os.replace(tmp_muxed, src_video)


def main():
    args = parse_args()
    in_path = Path(args.input).resolve()
    out_path = Path(args.output).resolve()

    if not in_path.exists():
        raise SystemExit(f"Input not found: {in_path}")

    print(f"🎬 Input:  {in_path}")
    print(f"📤 Output: {out_path}")
    print(f"🔎 Detect stride: {args.stride}, EMA smoothing: {args.smooth}, Letterbox: {args.letterbox}, Align: {args.letterbox_align}")

    # 1) Analyze positions (first pass)
    x_raw, W, H, fps_src, nframes = detect_xcenters(
        in_path,
        stride=args.stride,
        min_face_w=args.min_face,
        stick_frames=args.stick_frames,
        switch_area_ratio=args.switch_area_ratio,
        max_px_jump=args.max_px_jump,
        prefer_near_prev=not args.no_prefer_near_prev,
    )
    if not x_raw or nframes == 0:
        raise SystemExit("No frames read. Aborting.")

    x_smooth = ema_smooth(x_raw, alpha=args.smooth)
    x_smooth = np.clip(x_smooth, 0, W - 1)

    # 2) Crop geometry: vertical window width = H * 9/16 (clamped)
    crop_w = int(round(H * 9 / 16))
    crop_w = max(64, min(crop_w, W))
    half = crop_w / 2.0

    def x_center_at_idx(i):
        i = max(0, min(len(x_smooth) - 1, i))
        return float(x_smooth[i])

    def x1_at_idx(i):
        xc = x_center_at_idx(i)
        return max(0.0, min(W - crop_w, xc - half))  # left edge

    # 3) Second pass: write output video(s)
    TARGET_W, TARGET_H = 1080, 1920
    cap = cv2.VideoCapture(str(in_path))
    if not cap.isOpened():
        raise SystemExit(f"Failed to reopen input: {in_path}")

    fps_out = float(args.fps or (cap.get(cv2.CAP_PROP_FPS) or fps_src or 30.0))

    fourcc_try = ['avc1', 'H264', 'mp4v']
    writer = None
    for four in fourcc_try:
        fourcc = cv2.VideoWriter_fourcc(*four)
        writer = cv2.VideoWriter(str(out_path), fourcc, fps_out, (TARGET_W, TARGET_H))
        if writer.isOpened():
            print(f"🖊️  Using encoder fourcc: {four}")
            break
        writer.release()
        writer = None
    if writer is None:
        raise SystemExit("Could not open VideoWriter with avc1/H264/mp4v. Check OpenCV ffmpeg build.")

    # Optional SxS debug writer
    sbs_writer = None
    debug_out_path = out_path.with_name(out_path.stem + "_debug" + out_path.suffix)
    if args.debug_sbs:
        sbs_w = W + TARGET_W
        sbs_h = max(H, TARGET_H)
        for four in fourcc_try:
            fourcc = cv2.VideoWriter_fourcc(*four)
            sbs_writer = cv2.VideoWriter(str(debug_out_path), fourcc, fps_out, (sbs_w, sbs_h))
            if sbs_writer.isOpened():
                print(f"🖊️  Using encoder fourcc for SxS: {four}")
                break
            sbs_writer.release()
            sbs_writer = None
        if sbs_writer is None:
            print("⚠️ Could not open SxS writer; continuing without SxS.")
            args.debug_sbs = False

    # Optional CSV
    csv_file = None
    csv_writer = None
    if args.export_csv:
        csv_file = open(out_path.with_suffix(".csv"), "w", newline="")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["frame", "x_raw", "x_smooth", "x1_left"])

    # Letterbox factor (clamped) and placement
    lb = max(0.5, min(1.0, args.letterbox))
    inner_w = int(round(TARGET_W * lb))
    inner_h = int(round(TARGET_H * lb))
    x0_inner = (TARGET_W - inner_w) // 2
    if args.letterbox_align == "top":
        y0_inner = 0                           # padding only at bottom
    elif args.letterbox_align == "bottom":
        y0_inner = TARGET_H - inner_h          # padding only at top
    else:
        y0_inner = (TARGET_H - inner_h) // 2   # centered

    frame_idx = 0
    while True:
        ok, frame_bgr = cap.read()
        if not ok:
            break

        frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

        x1 = int(round(x1_at_idx(frame_idx)))
        x2 = x1 + crop_w
        x1 = max(0, min(x1, W - 1))
        x2 = max(1, min(x2, W))
        if x2 <= x1:
            x2 = min(W, x1 + 1)

        # Crop to the vertical window
        cropped = frame[:, x1:x2]

        # Create the 1080x1920 black canvas and place inner resized crop
        canvas_v = np.zeros((TARGET_H, TARGET_W, 3), dtype=np.uint8)
        inner_rgb = cv2.resize(cropped, (inner_w, inner_h), interpolation=cv2.INTER_AREA)
        canvas_v[y0_inner:y0_inner+inner_h, x0_inner:x0_inner+inner_w] = cv2.cvtColor(inner_rgb, cv2.COLOR_RGB2BGR)
        writer.write(canvas_v)

        # Optional SxS (left: original; right: letterboxed vertical)
        if args.debug_sbs:
            left = frame.copy()
            if args.debug_overlay:
                cv2.rectangle(left, (int(x1), 0), (int(x2), H-1), (0, 255, 255), 2)
                xc = int(x1 + crop_w/2)
                cv2.line(left, (xc, 0), (xc, H-1), (0, 255, 0), 2)
                xs = int(x_center_at_idx(frame_idx))
                cv2.circle(left, (xs, H//2), 6, (255, 0, 255), -1)
            left_bgr = cv2.cvtColor(left, cv2.COLOR_RGB2BGR)

            right_canvas = np.zeros((TARGET_H, TARGET_W, 3), dtype=np.uint8)
            right_canvas[y0_inner:y0_inner+inner_h, x0_inner:x0_inner+inner_w] = cv2.cvtColor(inner_rgb, cv2.COLOR_RGB2BGR)

            sbs_h = max(H, TARGET_H)
            sbs_w = W + TARGET_W
            sbs_can = np.zeros((sbs_h, sbs_w, 3), dtype=np.uint8)
            sbs_can[0:H, 0:W] = left_bgr
            sbs_can[0:TARGET_H, W:W+TARGET_W] = right_canvas
            sbs_writer.write(sbs_can)

        if csv_writer is not None:
            csv_writer.writerow([
                frame_idx,
                f"{x_raw[frame_idx]:.3f}" if frame_idx < len(x_raw) else "",
                f"{x_smooth[frame_idx]:.3f}" if frame_idx < len(x_smooth) else "",
                f"{x1:.3f}",
            ])

        frame_idx += 1

    cap.release()
    writer.release()
    if sbs_writer is not None:
        sbs_writer.release()
    if csv_file is not None:
        csv_file.close()

    # 4) Mux audio back from the original using ffmpeg
    ffmpeg_bin = "ffmpeg"  # change to full path if needed
    try:
        tmp_audio = out_path.with_suffix(".m4a")
        print("🔊 Muxing original audio into vertical output...")
        mux_audio(ffmpeg_bin, out_path, in_path, tmp_audio)
        try:
            if tmp_audio.exists():
                tmp_audio.unlink()
        except Exception:
            pass
        print("✅ Audio mux complete.")
    except Exception as e:
        print(f"⚠️ Audio mux failed ({e}). Video saved without audio: {out_path}")

    print("✅ Done.")


if __name__ == "__main__":
    main()
