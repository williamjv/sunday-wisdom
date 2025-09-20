# gather_wisdom

This directory contains scripts and workflows for gathering Sunday wisdom from sermon videos and sending summary emails to the worship director.

## Workflow
- Waits for Dropbox sync and finds new sermon videos.
- Converts video to audio, transcribes with Whisper, and extracts wisdom with Fabric.
- Cleans up intermediate files.
- Sends summary email with wisdom to the worship director.
- Archives old files to Google Drive and YouTube live videos.

## Main Scripts
- `sunday-wisdom.sh`: Orchestrates the full pipeline.
- `send-mail.py`: Sends summary emails via Gmail API.
- `archive-youtube-live-videos.py`: Archives YouTube live streams using Google API.

## Usage
Run the full pipeline:

```bash
bash sunday-wisdom.sh [--debug]
```

Check logs in `/home/william/logs/sunday-wisdom/`.

See script docstrings for more details.