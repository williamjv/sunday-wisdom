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
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import subprocess

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "../shared/archive-youtube-credentials.json")


def get_latest_nonlive_video_id(youtube, channel_id):
    # Get uploads playlist
    channels_response = youtube.channels().list(
        part="contentDetails",
        id=channel_id
    ).execute()
    uploads_playlist = channels_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    # Get latest videos
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
        # Exclude live videos
        if "liveStreamingDetails" not in video:
            return video_id
    return None

def main():
    parser = argparse.ArgumentParser(description="Download latest non-live YouTube video from a channel.")
    parser.add_argument("--channel-id", required=True, help="YouTube channel ID")
    parser.add_argument("--output", default="sermon.mp4", help="Output filename")
    args = parser.parse_args()

    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    youtube = build("youtube", "v3", credentials=creds)
    video_id = get_latest_nonlive_video_id(youtube, args.channel_id)
    if not video_id:
        print("No non-live video found.")
        sys.exit(1)
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"Downloading: {video_url}")
    subprocess.run(["yt-dlp", "-o", args.output, video_url], check=True)
    print(f"Downloaded to {args.output}")

if __name__ == "__main__":
    main()
