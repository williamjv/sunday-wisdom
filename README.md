# sunday-wisdom

Automates the end-to-end workflow for sermon video processing, wisdom extraction, YouTube Shorts creation, and notification for weekly church services.

## Directory Structure

- `gather_wisdom/` — Scripts and workflows for gathering Sunday wisdom from sermon videos and sending summary emails to the worship director.
- `shorts_maker/` — Scripts for generating YouTube Shorts from wisdom files and final YouTube videos.
- `shared/` — (Optional) Shared utilities or code used by both workflows.
- `.github/` — Project-specific instructions and configuration for AI coding agents.

## Main Workflows

### 1. Gather Wisdom
- Waits for Dropbox sync and finds new sermon videos.
- Converts video to audio, transcribes with Whisper, and extracts wisdom with Fabric.
- Cleans up intermediate files.
- Sends summary email with wisdom to the worship director.
- Archives old files to Google Drive and YouTube live videos.

See `gather_wisdom/README.md` for details.

### 2. Shorts Maker
- Downloads the final video from YouTube (posted by the worship director).
- Parses wisdom files for `# VIDEO CLIP SUGGESTIONS:` blocks.
- Cuts clips using ffmpeg.
- Optionally, reframes videos vertically (9:16) using OpenCV face detection.

See `shorts_maker/README.md` for details.

## Developer Notes
- All logs are stored in `/home/william/logs/sunday-wisdom/`.
- Credentials for Google/Gmail/YouTube APIs are stored in the project root as `*.json`/`*.pickle`.
- Paths to binaries/scripts are hardcoded in shell scripts; update as needed for your environment.

## Getting Started

1. Review the `README.md` in each subdirectory for workflow-specific setup and usage.
2. Run the main pipeline with:
   ```bash
   cd gather_wisdom
   bash sunday-wisdom.sh [--debug]
   ```
3. To generate Shorts, see the instructions in `shorts_maker/`.

---
For more details on project conventions and architecture, see `.github/copilot-instructions.md`.