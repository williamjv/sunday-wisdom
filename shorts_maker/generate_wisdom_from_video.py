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
import logging
import sys


WHISPER_BIN = "whisper"  # Assumes whisper is in PATH
FABRIC_BIN = "fabric"    # Assumes fabric is in PATH
PROMPT_PATH = os.path.join(os.path.dirname(__file__), "../shared/custompatterns/extract_wisdom_sermon_yt_short/system.md")
LOG_FILE = os.path.join(os.path.dirname(__file__), "generate_wisdom_from_video.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def main():
    parser = argparse.ArgumentParser(description="Transcribe video and generate wisdom suggestions.")
    parser.add_argument("--video", required=True, help="Input video file")
    parser.add_argument("--wisdom-out", default="wisdom.txt", help="Output wisdom file")
    parser.add_argument("--transcript-out", default="transcript.txt", help="Output transcript file")
    args = parser.parse_args()

    try:
        # 1. Transcribe
        print(f"Transcribing {args.video}...")
        logging.info(f"Transcribing {args.video}...")
        # Whisper CLI: whisper <audio_file> --model medium --language en --output_format txt > transcript.txt
        with open(args.transcript_out, "w") as transcript_out:
            result = subprocess.run([
                WHISPER_BIN, args.video, "--model", "medium", "--language", "en", "--output_format", "txt"
            ], stdout=transcript_out, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            logging.error(f"Whisper failed: {result.stderr}")
            print(f"Whisper failed: {result.stderr}")
            return 2
        if not os.path.exists(args.transcript_out):
            msg = f"Transcript file {args.transcript_out} not found after transcription."
            logging.error(msg)
            print(msg)
            return 3

        # 2. Generate wisdom
        print(f"Generating wisdom suggestions with Fabric AI...")
        logging.info(f"Generating wisdom suggestions with Fabric AI...")
        with open(args.transcript_out, "r") as transcript, open(args.wisdom_out, "w") as wisdom:
            result = subprocess.run([
                FABRIC_BIN, "--pattern", PROMPT_PATH
            ], stdin=transcript, stdout=wisdom, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                logging.error(f"Fabric failed: {result.stderr}")
                print(f"Fabric failed: {result.stderr}")
                return 4
        if not os.path.exists(args.wisdom_out):
            msg = f"Wisdom file {args.wisdom_out} not found after Fabric run."
            logging.error(msg)
            print(msg)
            return 5
        print(f"Wisdom suggestions written to {args.wisdom_out}")
        logging.info(f"Wisdom suggestions written to {args.wisdom_out}")
        return 0
    except Exception as e:
        logging.error(f"Pipeline failed: {e}")
        print(f"Pipeline failed: {e}")
        return 99

if __name__ == "__main__":
    sys.exit(main())
