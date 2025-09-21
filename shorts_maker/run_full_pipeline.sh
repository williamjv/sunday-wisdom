#!/bin/bash
# Run the full YouTube Shorts automation pipeline
# Assumes all scripts are in shorts_maker/ and credentials are in ../shared/
# Usage: bash run_full_pipeline.sh <YOUTUBE_CHANNEL_ID>


set -e
LOG_FILE="pipeline_run.log"
exec > >(tee -a "$LOG_FILE") 2>&1
echo "========== $(date) Starting Shorts Pipeline =========="


CHANNEL_ID="$1"
if [ -z "$CHANNEL_ID" ]; then
  echo "Usage: $0 <YOUTUBE_CHANNEL_ID>"
  exit 1
fi

fail() {
  echo "[ERROR] $1"
  echo "[ERROR] $1" >> "$LOG_FILE"
  exit 99
}


# 1. Download latest non-live video
echo "[1/5] Downloading latest non-live video..."
python3 download_latest_youtube.py --channel-id "$CHANNEL_ID" --output sermon.mp4 || fail "Failed to download latest YouTube video."


# 2. Transcribe and generate wisdom
echo "[2/5] Transcribing and generating wisdom..."
python3 generate_wisdom_from_video.py --video sermon.mp4 --wisdom-out wisdom.txt --transcript-out transcript.txt || fail "Failed to transcribe or generate wisdom."


# 3. Make up to 5 shorts
echo "[3/5] Generating up to 5 Shorts..."
mkdir -p shorts
python3 make_shorts_from_wisdom.py --wisdom-file wisdom.txt --base-dir . --outdir ./shorts --vertical-smart --max-clips 5 || fail "Failed to generate Shorts."


# 4. Upload and schedule Shorts
echo "[4/5] Uploading and scheduling Shorts..."
# Get the original video URL from the download script (reconstruct from video ID)
VIDEO_ID=$(yt-dlp --get-id sermon.mp4)
SOURCE_URL="https://www.youtube.com/watch?v=$VIDEO_ID"
python3 upload_and_schedule_shorts.py --shorts-dir ./shorts --source-url "$SOURCE_URL" || fail "Failed to upload or schedule Shorts."

echo "[5/5] Pipeline complete!"
echo "========== $(date) Shorts Pipeline Finished =========="
