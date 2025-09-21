#!/usr/bin/env python3
"""
Download the latest non-live video from a YouTube channel.
- Uses YouTube Data API to find the latest non-live upload.
- Downloads the video using yt-dlp.
- Requires credentials in ../shared/archive-youtube-credentials.json
"""
import os
import sys
import argparse
import logging
import pickle
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import subprocess



SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "../shared/archive-youtube-credentials.pickle")
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "../shared/archive-youtube-credentials.json")
LOG_FILE = os.path.join(os.path.dirname(__file__), "download_latest_youtube.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


def get_latest_nonlive_video_id(youtube, channel_id):
    try:
        channels_response = youtube.channels().list(
            part="contentDetails",
            id=channel_id
        ).execute()
        uploads_playlist = channels_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        playlist_response = youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_playlist,
            maxResults=10
        ).execute()
        for item in playlist_response["items"]:
            video_id = item["contentDetails"]["videoId"]
            video_response = youtube.videos().list(
                part="snippet,liveStreamingDetails",
                id=video_id
            ).execute()
            video = video_response["items"][0]
            if "liveStreamingDetails" not in video:
                return video_id
        return None
    except Exception as e:
        logging.error(f"Error fetching latest non-live video: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Download latest non-live YouTube video from a channel.")
    parser.add_argument("--channel-id", required=True, help="YouTube channel ID")
    parser.add_argument("--output", default="sermon.mp4", help="Output filename")
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
        video_id = get_latest_nonlive_video_id(youtube, args.channel_id)
        if not video_id:
            msg = "No non-live video found."
            print(msg)
            logging.error(msg)
            sys.exit(1)
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        print(f"Downloading: {video_url}")
        logging.info(f"Downloading: {video_url}")
        result = subprocess.run(["yt-dlp", "-o", args.output, video_url], capture_output=True, text=True)
        if result.returncode != 0:
            logging.error(f"yt-dlp failed: {result.stderr}")
            print(f"yt-dlp failed: {result.stderr}")
            sys.exit(2)
        print(f"Downloaded to {args.output}")
        logging.info(f"Downloaded to {args.output}")
    except Exception as e:
        logging.error(f"Pipeline failed: {e}")
        print(f"Pipeline failed: {e}")
        sys.exit(99)

if __name__ == "__main__":
    main()
