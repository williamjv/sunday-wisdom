import argparse
import os
import base64
import datetime
import logging
from email.message import EmailMessage
from logging.handlers import TimedRotatingFileHandler
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ========== Logging Setup ==========
LOG_DIR = '/home/william/logs/sunday-wisdom'
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, 'send-mail.log')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

handler = TimedRotatingFileHandler(
    log_file,
    when='D',         # Rotate weekly
    interval=1,       # Every 1 week
    backupCount=4    # Keep last 4 logs (4 weeks)
)
formatter = logging.Formatter(
    '%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.addHandler(logging.StreamHandler())  # Optional: also print to console


# ========== Gmail Setup ==========
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def get_last_sunday():
    today = datetime.date.today()
    offset = (today.weekday() + 1) % 7
    last_sunday = today - datetime.timedelta(days=offset)
    return last_sunday.strftime("%B %d, %Y")

def authenticate_gmail():
    creds = None
    token_file = '../shared/send-mail-token.json'
    credentials_file = '../shared/send-mail-credentials.json'

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    # Try refreshing if possible
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as refresh_error:
            logging.error(f"⚠️ Token refresh failed: {refresh_error}")
            creds = None
            if os.path.exists(token_file):
                os.remove(token_file)
                logging.info("🗑️ Deleted expired token file. Will re-authenticate.")

    # If no valid credentials, perform OAuth flow
    if not creds or not creds.valid:
        logging.info("🔑 Starting OAuth login flow (headless mode)...")
        flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
        creds = flow.run_console()  # ← Headless mode: terminal link + paste code
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
        logging.info("✅ New token created and saved.")

    return build('gmail', 'v1', credentials=creds)


def create_message_with_attachments(sender, to, subject, body_text, files_dir, files_list):
    message = EmailMessage()
    message.set_content(body_text)
    message['To'] = ', '.join(to)
    message['From'] = sender
    message['Subject'] = subject

    attached_files = []
    for file_name in files_list:
        file_path = os.path.join(files_dir, file_name)
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                file_data = f.read()
                message.add_attachment(
                    file_data,
                    maintype='application',
                    subtype='octet-stream',
                    filename=file_name
                )
            logging.info(f"📎 Attached: {file_name}")
            attached_files.append(file_path)
        else:
            logging.warning(f"⚠️ Missing: {file_name} (skipped)")

    if not attached_files:
        logging.warning("🚫 No wisdom files found. Email will not be sent.")
        return None, []

    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {'raw': encoded_message}, attached_files

def send_email(retry=False, override_to=None):
    try:
        service = authenticate_gmail()
        sender = 'william@charlotteag.org'
        to = override_to if override_to else ['sunday-wisdom@charlotteag.org']
        sunday_date = get_last_sunday()
        subject = f"Sunday Wisdom Files – {sunday_date}"
        body_text = f"Attached are the wisdom files from our Sunday service on {sunday_date}."
        files_dir = 'tmp'
        wisdom_files = ['1st_service_wisdom.txt', '2nd_service_wisdom.txt']

        message, attached_file_paths = create_message_with_attachments(
            sender, to, subject, body_text, files_dir, wisdom_files
        )

        if message:
            sent = service.users().messages().send(userId='me', body=message).execute()
            logging.info(f"✅ Email sent! Message ID: {sent['id']}")
            for file_path in attached_file_paths:
                try:
                    os.remove(file_path)
                    logging.info(f"🧹 Removed: {file_path}")
                except Exception as e:
                    logging.error(f"⚠️ Could not delete {file_path}: {e}")
        else:
            logging.info("📭 Email not sent because no attachments were found.")
    except Exception as e:
        logging.exception(f"❌ Failed to send email: {e}")
        # Retry once if not already retried
        if not retry:
            logging.info("🔁 Retrying send_email after error...")
            send_email(retry=True)
        else:
            logging.error("🚫 Retry failed. Giving up.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Send Sunday wisdom files via email.")
    parser.add_argument('--debug', action='store_true', help="Send only to william@charlotteag.org")
    args = parser.parse_args()

    if args.debug:
        logging.info("🐞 Debug mode enabled. Sending only to william@charlotteag.org")
        send_email(override_to=['william@charlotteag.org'])
    else:
        send_email()


