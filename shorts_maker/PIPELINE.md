# YouTube Shorts Automation Pipeline

This document describes the end-to-end workflow for automatically generating and uploading YouTube Shorts from a sermon video posted to your YouTube channel.

## Overview
This pipeline:
1. Downloads the latest non-Live video uploaded to your YouTube channel.
2. Uses Fabric AI (with a custom prompt) to generate YouTube Shorts suggestions.
3. Utilizes scripts in this directory to create up to 5 vertical Shorts.
4. Uploads the Shorts to your YouTube channel, scheduling them to publish one per day at 4pm EST.
5. Links each Short to the original full-length video.

---

## Step-by-Step Workflow

### 1. Download the Latest Non-Live YouTube Video
- Use the YouTube Data API to list recent uploads and filter out live videos.
- Download the latest eligible video using `yt-dlp` or a similar tool.
- Credentials for API access are in `../shared/` (e.g., `archive-youtube-credentials.json`).

### 2. Generate Short Suggestions with Fabric AI
- Transcribe the downloaded video (e.g., with Whisper).
- Use Fabric AI with the custom prompt in `../shared/custompatterns/extract_wisdom_sermon_yt_short/system.md` to extract up to 5 short-worthy moments.
- Save the output as a wisdom file for the next step.

### 3. Create Shorts
- Run `make_shorts_from_wisdom.py` with the generated wisdom file and the downloaded video.
- Use the `--vertical-smart` flag to enable speaker-centered vertical cropping.
- Limit output to 5 Shorts (see script options).

### 4. Upload and Schedule Shorts
- Use the YouTube Data API (with credentials from `../shared/`) to upload each Short.
- Schedule each Short to publish at 4pm EST on consecutive days.
- Include a link to the original video in each Short's description.

### 5. Link Shorts to Source Video
- Add the original video URL in the Shorts' descriptions or comments for easy navigation.

---

## Credentials
- All YouTube API credentials are stored in the `../shared/` directory.
- The same credentials used for archiving can be used for Shorts upload and scheduling.

---

## Example Orchestration (Pseudocode)

```bash
# 1. Download latest non-live video
yt-dlp <video_url> -o sermon.mp4

# 2. Transcribe and generate wisdom
whisper sermon.mp4 --output transcript.txt
fabric --pattern ../shared/custompatterns/extract_wisdom_sermon_yt_short/system.md < transcript.txt > wisdom.txt

# 3. Make shorts
python3 make_shorts_from_wisdom.py --wisdom-file wisdom.txt --base-dir . --outdir ./shorts --vertical-smart --max-clips 5

# 4. Upload and schedule (custom script needed)
python3 upload_and_schedule_shorts.py --shorts-dir ./shorts --credentials ../shared/archive-youtube-credentials.json --source-url <original_video_url>
```

---

## Notes
- Error handling, logging, and notification are recommended for production use.
- You may need to write or adapt a script for the upload/scheduling step (see YouTube Data API docs).
- All times should be converted to UTC for YouTube scheduling.

For more details, see the scripts and docstrings in this directory.