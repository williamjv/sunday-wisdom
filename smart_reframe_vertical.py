 #!/usr/bin/env python3
"""
Smart vertical reframing for speaker-centric Shorts, with debugging tools.

- Detects face with OpenCV Haar cascade
- Tracks/EMA-smooths the x-center over time
- Crops to a vertical 9:16 window that follows the speaker
- Outputs 1080x1920 H.264 + AAC

Debugging:
  --debug-overlay   Draw crop rectangle & smoothed center on original frames (for SxS preview).
  --debug-sbs       Also write a side-by-side (original|vertical) debug video: <output>_debug.mp4
  --export-csv      Save per-frame positions to CSV: <output>.csv

Usage:
  python3 smart_reframe_vertical.py -i input.mp4 -o output.mp4
  python3 smart_reframe_vertical.py -i input.mp4 -o output.mp4 --stride 5 --smooth 0.85 --debug-overlay --debug-sbs --export-csv
"""

import argparse
import csv
import os
from pathlib import Path
import numpy as np
import cv2
from moviepy.editor import VideoFileClip, clips_array

def parse_args():
    ap = argparse.ArgumentParser(description="Auto-center speaker and reframe to vertical 9:16 (1080x1920).")
    ap.add_argument("-i", "--input", required=True, help="Input video (landscape)")
    ap.add_argument("-o", "--output", required=True, help="Output vertical video (mp4)")
    ap.add_argument("--stride", type=int, default=5, help="Detect every Nth frame (default 5)")
    ap.add_argument("--smooth", type=float, default=0.8, help="EMA smoothing factor (0..1). Higher = steadier.")
    ap.add_argument("--min-face", type=int, default=60, help="Minimum face width for detection (px)")
    ap.add_argument("--fps", type=int, default=None, help="Override output FPS (default: source)")
    ap.add_argument("--preset", default="veryfast", help="x264 preset (passed to ffmpeg)")
    ap.add_argument("--crf", type=int, default=23, help="x264 CRF")
    # Debug extras
    ap.add_argument("--debug-overlay", action="store_true",
                    help="Draw crop window & smoothed center on original frames (for SxS preview).")
    ap.add_argument("--debug-sbs", action="store_true",
                    help="Write side-by-side debug video: <output>_debug.mp4 (Original|Vertical).")
    ap.add_argument("--export-csv", action="store_true",
                    help="Export per-frame positions to CSV: <output>.csv")
    return ap.parse_args()

def detect_xcenters(video_path: Path, stride: int, min_face_w: int):
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
    last_x_center = W / 2.0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if stride <= 1 or frame_idx % stride == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5,
                minSize=(min_face_w, min_face_w)
            )
            if len(faces) > 0:
                x, y, w, h = max(faces, key=lambda f: f[2]*f[3])
                last_x_center = x + w / 2.0
        xcenters_raw.append(last_x_center)
        frame_idx += 1

    cap.release()
    return xcenters_raw, W, H, fps

def ema_smooth(data, alpha: float) -> np.ndarray:
    if not data:
        return np.array([])
    out = np.zeros(len(data), dtype=np.float32)
    out[0] = data[0]
    for i in range(1, len(data)):
        out[i] = alpha * out[i-1] + (1 - alpha) * data[i]
    return out

def main():
    args = parse_args()
    in_path = Path(args.input)
    out_path = Path(args.output)
    if not in_path.exists():
        raise SystemExit(f"Input not found: {in_path}")

    print(f"🎬 Input:  {in_path}")
    print(f"📤 Output: {out_path}")
    print(f"🔎 Detect stride: {args.stride}, EMA smoothing: {args.smooth}")

    # 1) Analyze positions
    x_raw, W, H, fps_src = detect_xcenters(in_path, stride=args.stride, min_face_w=args.min_face)
    if not x_raw:
        raise SystemExit("No frames read. Aborting.")
    x_smooth = ema_smooth(x_raw, alpha=args.smooth)
    x_smooth = np.clip(x_smooth, 0, W - 1)

    # 2) Crop geometry: keep full height, crop width = H * 9/16 (clamped)
    crop_w = int(round(H * 9 / 16))
    crop_w = max(64, min(crop_w, W))
    half = crop_w / 2.0

    # Helper functions
    def x_center_at_t(t, fps_for_index):
        idx = int(round(t * fps_for_index))
        idx = max(0, min(len(x_smooth) - 1, idx))
        return float(x_smooth[idx])

    def x1_at_t(t, fps_for_index):
        xc = x_center_at_t(t, fps_for_index)
        return max(0.0, min(W - crop_w, xc - half))

    # 3) Build MoviePy pipeline
    clip = VideoFileClip(str(in_path))
    fps_out = args.fps or clip.fps or fps_src or 30

    # Vertical final
    cropped = clip.crop(x1=lambda t: x1_at_t(t, clip.fps or fps_src or 30), width=crop_w, height=clip.h)
    final_vertical = cropped.resize((1080, 1920))

    # 4) Optional debug: overlay & side-by-side
    debug_out_path = out_path.with_name(out_path.stem + "_debug" + out_path.suffix)

    def draw_overlay(frame, t):
        # Draw crop box & center line on original frame
        x1 = x1_at_t(t, clip.fps or fps_src or 30)
        x2 = x1 + crop_w
        h, w = frame.shape[:2]
        # rectangle
        cv2.rectangle(frame, (int(x1), 0), (int(x2), h-1), (0, 255, 255), 2)
        # center line of crop
        xc = int(x1 + crop_w/2)
        cv2.line(frame, (xc, 0), (xc, h-1), (0, 255, 0), 2)
        # smoothed x-center (dot)
        xs = int(x_center_at_t(t, clip.fps or fps_src or 30))
        cv2.circle(frame, (xs, h//2), 6, (255, 0, 255), -1)
        return frame

    if args.debug_overlay or args.debug_sbs:
        dbg_clip = clip.fl(lambda gf, t: draw_overlay(gf(t).copy(), t))
        # If SxS requested, write combined output
        if args.debug_sbs:
            # Make heights equal for concat
            target_h = 720
            left = dbg_clip.resize(height=target_h)
            right = final_vertical.resize(height=target_h)
            sbs = clips_array([[left, right]])
            print(f"🛠  Writing debug SxS to {debug_out_path}")
            sbs.write_videofile(
                str(debug_out_path),
                fps=fps_out,
                codec="libx264",
                audio_codec="aac",
                preset=args.preset,
                ffmpeg_params=["-crf", str(args.crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
                threads=os.cpu_count() or 4
            )

    # 5) Export CSV if requested
    if args.export_csv:
        csv_path = out_path.with_suffix(".csv")
        print(f"🧾 Writing CSV: {csv_path}")
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["frame", "time_sec", "x_raw", "x_smooth", "x1_left"])
            fps_index = clip.fps or fps_src or 30
            for i in range(len(x_smooth)):
                t = i / fps_index
                writer.writerow([i, f"{t:.3f}", f"{x_raw[i]:.3f}", f"{x_smooth[i]:.3f}", f"{max(0.0, min(W - crop_w, x_smooth[i] - half)):.3f}"])

    # 6) Write main vertical output
    print(f"🛠  Writing vertical output to {out_path}")
    final_vertical.write_videofile(
        str(out_path),
        fps=fps_out,
        codec="libx264",
        audio_codec="aac",
        preset=args.preset,
        ffmpeg_params=["-crf", str(args.crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
        threads=os.cpu_count() or 4
    )

    # Cleanup
    clip.close()
    cropped.close()
    final_vertical.close()
    print("✅ Done.")

if __name__ == "__main__":
    main()
