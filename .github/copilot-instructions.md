# Copilot Instructions for `sunday-wisdom`

## Project Overview
- **Purpose:** Automates sermon video processing, wisdom extraction, YouTube Shorts creation, and notification email for weekly church services.
- **Main Workflow:** Orchestrated by `sunday-wisdom.sh`, which runs all major steps end-to-end.

## Key Components
- **Shell Pipeline:**
  - `sunday-wisdom.sh` is the entrypoint. It:
    - Waits for Dropbox sync, finds new sermon videos, and processes them.
    - Converts video to audio, transcribes with Whisper, extracts wisdom with Fabric, and cleans up intermediates.
    - (Optionally) Generates YouTube Shorts using `make_shorts_from_wisdom.py` and `smart_reframe_vertical.py`.
    - Sends summary emails (`send-mail.py`) and archives old files to Google Drive.
    - Archives YouTube live videos (`archive-youtube-live-videos.py`).
- **Python Scripts:**
  - `make_shorts_from_wisdom.py`: Parses wisdom files, finds video segments, and cuts clips (optionally reframes vertically).
  - `smart_reframe_vertical.py`: Crops landscape videos to vertical, centering on speaker using OpenCV face detection.
  - `send-mail.py`: Sends summary emails via Gmail API.
  - `archive-youtube-live-videos.py`: Archives YouTube live streams using Google API.

## Conventions & Patterns
- **File Naming:** Sermon videos: `YYYY-MM-DD HH-MM-SS.mp4` (date and time).
- **Service Detection:**
  - 1st service: < 11:00am
  - 2nd service: >= 11:15am
  - Only videos between 9am–1pm are kept.
- **Wisdom Extraction:**
  - Uses Fabric (`fabric --pattern extract_wisdom_sermon_simple`) on transcripts.
  - Wisdom files are parsed for `# VIDEO CLIP SUGGESTIONS:` blocks.
- **Shorts Generation:**
  - Controlled by commented-out section in `sunday-wisdom.sh` (uncomment to enable).
  - Uses `--vertical-smart` for speaker-centered vertical cropping.
- **Credentials:**
  - Google/Gmail/Youtube API credentials in root directory as `*.json`/`*.pickle`.
- **Logs:**
  - All logs in `/home/william/logs/sunday-wisdom/`. Rotated and cleaned after 30 days.

## Developer Workflows
- **Run full pipeline:** `bash sunday-wisdom.sh [--debug]`
- **Debugging:** Use `--debug` for verbose logs.
- **Add new wisdom extraction patterns:** Edit `make_shorts_from_wisdom.py` regexes.
- **Update video processing:** Edit `smart_reframe_vertical.py` for face detection/cropping logic.
- **Email/YouTube archiving:** Update respective Python scripts for API changes.

## External Dependencies
- Python 3, OpenCV, Whisper, ffmpeg, Fabric, Dropbox CLI, rclone, rsync, Google API Python libs.
- Paths to binaries/scripts are hardcoded in `sunday-wisdom.sh`.

## Examples
- To process a new Sunday: Place video in base dir, run the shell script, check logs and output in `shorts/` and `tmp/`.
- To generate Shorts: Ensure wisdom files exist, uncomment Shorts section in `sunday-wisdom.sh`, rerun script.

---
For questions about workflow or structure, see `sunday-wisdom.sh` and script docstrings for details.
