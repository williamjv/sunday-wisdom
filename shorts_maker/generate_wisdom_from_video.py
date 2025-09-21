#!/usr/bin/env python3
"""
Transcribe a video and generate YouTube Shorts suggestions using Fabric AI and a custom prompt.
- Uses Whisper for transcription.
- Uses Fabric AI with the prompt in ../shared/custompatterns/extract_wisdom_sermon_yt_short/system.md
- Outputs a wisdom file for use with make_shorts_from_wisdom.py
"""
import argparse
import os
import subprocess

WHISPER_BIN = "whisper"  # Assumes whisper is in PATH
FABRIC_BIN = "fabric"    # Assumes fabric is in PATH
PROMPT_PATH = os.path.join(os.path.dirname(__file__), "../shared/custompatterns/extract_wisdom_sermon_yt_short/system.md")

def main():
    parser = argparse.ArgumentParser(description="Transcribe video and generate wisdom suggestions.")
    parser.add_argument("--video", required=True, help="Input video file")
    parser.add_argument("--wisdom-out", default="wisdom.txt", help="Output wisdom file")
    parser.add_argument("--transcript-out", default="transcript.txt", help="Output transcript file")
    args = parser.parse_args()

    # 1. Transcribe
    print(f"Transcribing {args.video}...")
    subprocess.run([WHISPER_BIN, args.video, "--output_format", "txt", "--language", "en", "--model", "medium", "--output", args.transcript_out], check=True)

    # 2. Generate wisdom
    print(f"Generating wisdom suggestions with Fabric AI...")
    with open(args.transcript_out, "r") as transcript, open(args.wisdom_out, "w") as wisdom:
        subprocess.run([FABRIC_BIN, "--pattern", PROMPT_PATH], stdin=transcript, stdout=wisdom, check=True)
    print(f"Wisdom suggestions written to {args.wisdom_out}")

if __name__ == "__main__":
    main()
