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
import logging
import pickle
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pytz



SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "../shared/archive-youtube-credentials.pickle")
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "../shared/archive-youtube-credentials.json")
LOG_FILE = os.path.join(os.path.dirname(__file__), "upload_and_schedule_shorts.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


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
    try:
        with open(video_path, "rb") as video_file:
            request = youtube.videos().insert(
                part=",".join(body.keys()),
                body=body,
                media_body=video_path
            )
            response = request.execute()
            return response["id"]
    except Exception as e:
        logging.error(f"Failed to upload {video_path}: {e}")
        print(f"Failed to upload {video_path}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Upload and schedule YouTube Shorts.")
    parser.add_argument("--shorts-dir", required=True, help="Directory containing Shorts (mp4 files)")
    parser.add_argument("--source-url", required=True, help="URL of the original full-length video")
    parser.add_argument("--start-date", default=None, help="Date to start scheduling (YYYY-MM-DD, default: tomorrow)")
    args = parser.parse_args()

    try:
        creds = None
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'rb') as token:
                creds = pickle.load(token)
        if creds and creds.valid:
            logging.info("✅ Using existing valid credentials.")
        elif creds and creds.expired and creds.refresh_token:
            logging.info("🔄 Credentials expired, attempting refresh...")
            try:
                creds.refresh(Request())
                with open(TOKEN_FILE, 'wb') as token:
                    pickle.dump(creds, token)
                logging.info("✅ Credentials refreshed and saved.")
            except Exception as e:
                logging.error(f"❌ Token refresh failed: {e}")
                if os.path.exists(TOKEN_FILE):
                    os.remove(TOKEN_FILE)
                creds = None
        if not creds or not creds.valid:
            logging.info("⚠️ No valid credentials available. Starting new OAuth flow.")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, 'wb') as token:
                pickle.dump(creds, token)
            logging.info("✅ New credentials obtained and saved.")
        youtube = build("youtube", "v3", credentials=creds)

        shorts = sorted([f for f in os.listdir(args.shorts_dir) if f.endswith(".mp4")])
        if not shorts:
            msg = "No Shorts found in directory."
            print(msg)
            logging.error(msg)
            sys.exit(1)

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
            logging.info(f"Uploading {short} to be published at {publish_time_utc} UTC...")
            video_id = upload_short(youtube, video_path, title, description, publish_time_utc)
            if video_id:
                print(f"Uploaded: https://youtu.be/{video_id}")
                logging.info(f"Uploaded: https://youtu.be/{video_id}")
            else:
                logging.error(f"Failed to upload {short}")
            publish_time += datetime.timedelta(days=1)
        return 0
    except Exception as e:
        logging.error(f"Pipeline failed: {e}")
        print(f"Pipeline failed: {e}")
        return 99

if __name__ == "__main__":
    sys.exit(main())
