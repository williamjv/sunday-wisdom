import os
import argparse
import pickle
import datetime
import logging
from logging.handlers import TimedRotatingFileHandler
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError

SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
LOG_DIR = '/home/william/logs/sunday-wisdom'
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, 'archive_youtube.log')

logger = logging.getLogger()

# Console and file handler
handler = TimedRotatingFileHandler(
    log_file,
    when='D',         # Rotate daily
    interval=1,
    backupCount=14    # Keep last 2 weeks of logs
)
formatter = logging.Formatter(
    '%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.addHandler(logging.StreamHandler())  # Also print to console


def get_authenticated_service():
    creds = None
    token_file = 'archive-youtube-credentials.pickle'
    try:
        if os.path.exists(token_file):
            with open(token_file, 'rb') as token:
                creds = pickle.load(token)
        if creds and creds.valid:
            logging.info("✅ Using existing valid credentials.")
        elif creds and creds.expired and creds.refresh_token:
            logging.info("🔄 Credentials expired, attempting refresh...")
            try:
                creds.refresh(Request())
                with open(token_file, 'wb') as token:
                    pickle.dump(creds, token)
                logging.info("✅ Credentials refreshed and saved.")
            except Exception as e:
                logging.error(f"❌ Token refresh failed: {e}")
                logging.warning("⚠️ Token is invalid or revoked. Deleting the token and starting fresh auth flow.")
                if os.path.exists(token_file):
                    os.remove(token_file)
                # Retry with clean credentials
                return get_authenticated_service()
        else:
            logging.info("⚠️ No valid credentials available. Starting new OAuth flow.")
            flow = InstalledAppFlow.from_client_secrets_file('archive-youtube-credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

            with open(token_file, 'wb') as token:
                pickle.dump(creds, token)
            logging.info("✅ New credentials obtained and saved.")
    except Exception as e:
        logging.error(f"❌ Failed to authenticate: {e}")
        raise e

    return build('youtube', 'v3', credentials=creds)


def list_all_video_ids(youtube):
    video_ids = []
    request = youtube.channels().list(part="contentDetails", mine=True)
    response = request.execute()

    uploads_playlist_id = response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    next_page_token = None

    while True:
        playlist_request = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=50,
            pageToken=next_page_token
        )
        playlist_response = playlist_request.execute()
        for item in playlist_response["items"]:
            video_ids.append(item["contentDetails"]["videoId"])

        next_page_token = playlist_response.get("nextPageToken")
        if not next_page_token:
            break
    return video_ids


def get_video_details(youtube, video_ids):
    video_data = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i + 50]
        request = youtube.videos().list(
            part="id,snippet,liveStreamingDetails,status",
            id=",".join(chunk)
        )
        response = request.execute()
        for item in response["items"]:
            video_id = item["id"]
            snippet = item["snippet"]
            status = item["status"]
            live_details = item.get("liveStreamingDetails", {})

            title = snippet["title"]
            published_at = snippet["publishedAt"]
            visibility = status["privacyStatus"]
            live_broadcast_content = snippet.get("liveBroadcastContent", "none")
            end_time = live_details.get("actualEndTime")

            is_past_live = bool(end_time)

            logging.debug(f"🧾 Video: {title}")
            logging.debug(f"   ID: {video_id}")
            logging.debug(f"   Published: {published_at}")
            logging.debug(f"   Visibility: {visibility}")
            logging.debug(f"   Live Status: {live_broadcast_content}")
            logging.debug(f"   End Time: {end_time}")
            logging.debug(f"   Is Past Live: {is_past_live}\n")

            video_data.append({
                "id": video_id,
                "title": title,
                "published_at": published_at,
                "visibility": visibility,
                "live_broadcast_content": live_broadcast_content,
                "is_past_live": is_past_live,
                "end_time": end_time
            })
    return video_data


def archive_old_public_live_videos(dry_run=False, min_days=14, max_days=365):
    youtube = get_authenticated_service()
    logging.info("🔍 Fetching all uploaded video IDs...")
    video_ids = list_all_video_ids(youtube)
    logging.info(f"✅ Found {len(video_ids)} total uploaded videos.\n")

    videos = get_video_details(youtube, video_ids)

    now = datetime.datetime.now(datetime.timezone.utc)
    max_time = now - datetime.timedelta(days=max_days)
    min_time = now - datetime.timedelta(days=min_days)

    to_archive = []
    for video in videos:
        debug_reason = []
        should_archive = True

        if not video["is_past_live"]:
            should_archive = False
            debug_reason.append("Not a past live video")
        if video["visibility"] != "public":
            should_archive = False
            debug_reason.append(f"Visibility is '{video['visibility']}'")
        if not video["end_time"]:
            should_archive = False
            debug_reason.append("Missing end_time")

        try:
            if video["end_time"]:
                video_end = datetime.datetime.fromisoformat(video["end_time"].replace("Z", "+00:00"))
                if video_end >= min_time:
                    should_archive = False
                    debug_reason.append(f"End time is less than {min_days} days ago ({video_end})")
                if video_end <= max_time:
                    should_archive = False
                    debug_reason.append(f"End time is more than {max_days} days ago ({video_end})")
        except Exception as e:
            should_archive = False
            debug_reason.append(f"Failed to parse end_time: {e}")

        if should_archive:
            to_archive.append(video)
        elif dry_run:
            logging.warning(f"🚫 Skipping: {video['title']} (ID: {video['id']})")
            logging.warning(f"   📅 Published: {video['published_at']}")
            logging.warning(f"   🔒 Visibility: {video['visibility']}")
            logging.warning(f"   🎥 is_past_live: {video['is_past_live']}")
            logging.warning(f"   🕓 End Time: {video['end_time']}")
            logging.warning(f"   🧾 Reason(s): {', '.join(debug_reason)}\n")

    logging.info(f"🎯 Found {len(to_archive)} public live videos older than {min_days} days and newer than {max_days} days to archive.\n")

    for video in to_archive:
        logging.info(f"📝 Archiving: {video['title']} (ID: {video['id']})")
        logging.info(f"   📅 Published: {video['published_at']}")
        logging.info(f"   🔒 Visibility: {video['visibility']}")
        logging.info(f"   🎥 is_past_live: {video['is_past_live']}")
        logging.info(f"   🕓 End Time: {video['end_time']}")
        if dry_run:
            logging.info("   🧪 Dry-run mode: no changes made.\n")
        else:
            try:
                youtube.videos().update(
                    part="status",
                    body={
                        "id": video["id"],
                        "status": {
                            "privacyStatus": "private"
                        }
                    }
                ).execute()
                logging.info("   ✅ Visibility changed to private.\n")
            except Exception as e:
                logging.error(f"❌ Failed to archive {video['title']} (ID: {video['id']}): {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Archive old public live YouTube videos.")
    parser.add_argument('--dry-run', action='store_true', help="Only print actions, do not change video status.")
    parser.add_argument('--min-days', type=int, default=14, help="Minimum number of days old (default: 14)")
    parser.add_argument('--max-days', type=int, default=365, help="Maximum number of days old (default: 365)")
    parser.add_argument('--debug', action='store_true', help="Enable verbose logging")
    args = parser.parse_args()

    # Configure root logger
    
    logger.setLevel(logging.DEBUG if args.debug else logging.INFO)

    archive_old_public_live_videos(dry_run=args.dry_run, min_days=args.min_days, max_days=args.max_days)
