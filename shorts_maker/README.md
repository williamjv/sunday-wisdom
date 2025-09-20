# shorts_maker

This directory contains scripts for generating YouTube Shorts from sermon wisdom files and final YouTube videos.

## Workflow
- Download the final video from YouTube (posted by the worship director).
- Parse wisdom files for `# VIDEO CLIP SUGGESTIONS:` blocks.
- Cut clips using ffmpeg.
- Optionally, reframe videos vertically (9:16) using OpenCV face detection.

## Main Scripts
- `make_shorts_from_wisdom.py`: Parses wisdom files and generates clips.
- `smart_reframe_vertical.py`: Crops landscape videos to vertical, centering on the speaker.

## Usage
Run shorts generation (example):

```bash
python3 make_shorts_from_wisdom.py --wisdom-file <wisdom.txt> --base-dir <video_dir> --outdir <output_dir> --vertical-smart
```

See script docstrings for more details.