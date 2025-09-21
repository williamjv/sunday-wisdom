#!/usr/bin/env python3
"""
Upload and schedule YouTube Shorts from a directory.
- Uploads each short in the specified directory to YouTube as a Short.
- Schedules each to publish at 4pm EST on consecutive days.
- Adds a link to the source video in the description.
- Uses credentials from ../shared/archive-youtube-credentials.json
"""
import os
import sys
import argparse
import datetime
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import pytz

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "../shared/archive-youtube-credentials.json")


def upload_short(youtube, video_path, title, description, publish_time_utc):
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "22",  # People & Blogs
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_time_utc.isoformat(),
            "selfDeclaredMadeForKids": False,
        }
    }
    with open(video_path, "rb") as video_file:
        request = youtube.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=video_path
        )
        response = request.execute()
        return response["id"]

def main():
    parser = argparse.ArgumentParser(description="Upload and schedule YouTube Shorts.")
    parser.add_argument("--shorts-dir", required=True, help="Directory containing Shorts (mp4 files)")
    parser.add_argument("--source-url", required=True, help="URL of the original full-length video")
    parser.add_argument("--start-date", default=None, help="Date to start scheduling (YYYY-MM-DD, default: tomorrow)")
    args = parser.parse_args()

    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    youtube = build("youtube", "v3", credentials=creds)

    shorts = sorted([f for f in os.listdir(args.shorts_dir) if f.endswith(".mp4")])
    if not shorts:
        print("No Shorts found in directory.")
        sys.exit(1)

    # Start scheduling from tomorrow
    est = pytz.timezone("US/Eastern")
    if args.start_date:
        start_date = datetime.datetime.strptime(args.start_date, "%Y-%m-%d")
    else:
        start_date = datetime.datetime.now(est) + datetime.timedelta(days=1)
    publish_time = est.localize(start_date.replace(hour=16, minute=0, second=0, microsecond=0))

    for i, short in enumerate(shorts):
        video_path = os.path.join(args.shorts_dir, short)
        title = f"Sermon Short #{i+1}"
        description = f"Created from: {args.source_url}\n\n#shorts"
        publish_time_utc = publish_time.astimezone(pytz.utc)
        print(f"Uploading {short} to be published at {publish_time_utc} UTC...")
        video_id = upload_short(youtube, video_path, title, description, publish_time_utc)
        print(f"Uploaded: https://youtu.be/{video_id}")
        publish_time += datetime.timedelta(days=1)

if __name__ == "__main__":
    main()
