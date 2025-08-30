#!/bin/bash

set -e

# =====================
# Configuration
# =====================
BASE_DIR="/home/william/CAG Dropbox/Media/Sermon Recordigs"
SEND_MAIL="/home/william/scripts/PERSONAL/sunday-wisdom"
VENV_ACTIVATE="/home/william/scripts/PERSONAL/fabric/.venv/bin/activate"

# Binary paths (fully qualified)
FFMPEG_BIN="/usr/bin/ffmpeg"
WHISPER_BIN="/home/william/scripts/PERSONAL/fabric/.venv/bin/whisper"
FABRIC_BIN="/home/william/go/bin/fabric"
DROPBOX_BIN="/usr/bin/dropbox"
PYTHON_BIN="/home/william/scripts/PERSONAL/fabric/.venv/bin/python3"
RCLONE_BIN="/usr/bin/rclone"
RSYNC_BIN="/usr/bin/rsync"

# =====================
# Logging Setup
# =====================
LOG_DIR="/home/william/logs/sunday-wisdom"
mkdir -p "$LOG_DIR"

NOW=$(date +"%Y-%m-%d_%H-%M")
LOG_FILE="${LOG_DIR}/sermon_pipeline_${NOW}.log"
ln -sf "$LOG_FILE" "${LOG_DIR}/latest.log"

exec > >(tee -a "$LOG_FILE") 2>&1
echo "===================="
echo "📅 Run started: $(date)"
echo "===================="

# =====================
# Debug flag handling
# =====================
DEBUG=0  # Default: quiet mode
for arg in "$@"; do
    if [[ "$arg" == "--debug" ]]; then
        DEBUG=1
    fi
done

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*"
}

debug() {
    if [[ "$DEBUG" -eq 1 ]]; then
        log "$*"
    fi
}

# =====================
# Log Environment Info
# =====================
debug "🔧 Environment paths:"
debug "• ffmpeg:    $FFMPEG_BIN"
debug "• whisper:   $WHISPER_BIN"
debug "• fabric:    $FABRIC_BIN"
debug "• dropbox:   $DROPBOX_BIN"
debug "• python3:   $PYTHON_BIN"
debug "• rclone:    $RCLONE_BIN"
debug "• rsync:     $RSYNC_BIN"
debug "• VIRTUAL_ENV: $VIRTUAL_ENV"

# =====================
# Functions
# =====================
ensure_virtualenv_ready() {
    if [[ -z "$VIRTUAL_ENV" ]]; then
        log "⚠️  Virtual environment not active. Reactivating..."
        source "$VENV_ACTIVATE" || { log "❌ Failed to activate virtualenv"; exit 1; }
    else
        debug "✅ Virtual environment is active."
    fi

    if ! command -v "$FABRIC_BIN" &>/dev/null; then
        log "❌ 'fabric' command not found at $FABRIC_BIN. Is it installed?"
        exit 1
    fi
}

# =====================
# Start Processing
# =====================
cd "$BASE_DIR" || { log "❌ Directory not found: $BASE_DIR"; exit 1; }

log "🔍 Checking if Dropbox is running..."

if "$DROPBOX_BIN" running; then
    log "✅ Dropbox is already running."
else
    log "❌ Dropbox not running. Starting Dropbox..."
    "$DROPBOX_BIN" start
fi

log "⏳ Waiting for Dropbox to be 'Up to date'..."

spinner="/-\|"

while true; do
    status_output=$("$DROPBOX_BIN" status)
    log "📄 Dropbox status: $status_output"

    if [[ "$status_output" == "Up to date" ]]; then
        log "✅ Dropbox is Up to date. Continuing with the script."
        break
    fi

    debug "🕔 Checking again in 5 minutes..."
    for ((i=1; i<=300; i++)); do
        sleep 1
    done
done

# =====================
# Process Files
# =====================
latest_sunday=$(date -d "last sunday" +%Y-%m-%d)
log "🔍 Looking for MP4 files from $latest_sunday..."

mapfile -t sunday_files < <(find . -maxdepth 1 -name "${latest_sunday}*.mp4" | sort)

if [ "${#sunday_files[@]}" -eq 0 ]; then
    log "⚠️ No sermon videos found for $latest_sunday."
    exit 1
fi

ensure_virtualenv_ready

for video in "${sunday_files[@]}"; do
    filename=$(basename "$video")
    log "▶️ Found video: $filename"

    time_str=$(echo "$filename" | cut -d' ' -f2 | cut -d'.' -f1 | tr '-' ':')
    hour=$(echo "$time_str" | cut -d':' -f1)
    minute=$(echo "$time_str" | cut -d':' -f2)
    total_minutes=$((10#$hour * 60 + 10#$minute))

    # Delete videos outside the 9 AM – 1 PM window
    if (( total_minutes < 540 || total_minutes > 780 )); then
    echo "🗑 Deleting $filename (outside of 9am–1pm window)"
    /usr/bin/gio trash "$video"
    continue
    fi

    if (( total_minutes < 660 )); then
        service="1st_service"
    elif (( total_minutes >= 675 )); then
        service="2nd_service"
    else
        log "❓ Skipping ambiguous time: $filename"
        continue
    fi

    TMP_DIR="${SEND_MAIL}/tmp"
    mkdir -p "$TMP_DIR"

    audio_file="${TMP_DIR}/${service}.mp3"
    transcript_file="${TMP_DIR}/${service}.txt"
    wisdom_output="${TMP_DIR}/${service}_wisdom.txt"
    summarize_output="${TMP_DIR}/${service}_summarized.txt"

    log "🎙 Processing $filename as $service"
    log "🎧 Converting to audio: $audio_file"
    "$FFMPEG_BIN" -i "$video" -vn -acodec mp3 "$audio_file"

    log "📝 Transcribing $audio_file..."
    "$WHISPER_BIN" "$audio_file" --model medium --language en --output_format txt > "$transcript_file"

    log "💡 Extracting wisdom from $transcript_file..."
    cat "$transcript_file" | "$FABRIC_BIN" --pattern extract_wisdom_sermon > "$wisdom_output"

    log "🧹 Cleaning up intermediate files..."
    log "🗑 Deleting MP3: ${audio_file}" && rm "${audio_file}"
    log "🗑 Deleting Transcript: ${transcript_file}" && rm "${transcript_file}"
done

log "📧 Calling Email Script..."
cd "$SEND_MAIL"
"$PYTHON_BIN" send-mail.py

if ! mount | grep -q "/home/william/GoogleDrive"; then
    log "🔗 Mounting Google Drive..."
    "$RCLONE_BIN" mount "Google Drive:" /home/william/GoogleDrive --daemon
    sleep 5
else
    debug "✅ Google Drive already mounted."
fi

log "📦 Archiving recordings older than 30 days..."

find "$BASE_DIR" -type f -mtime +30 -print0 | while IFS= read -r -d '' file; do
  filename=$(basename "$file")
  
  # Extract year from filename (assumes YYYY-MM-DD at the start)
  if [[ "$filename" =~ ^([0-9]{4})- ]]; then
    year="${BASH_REMATCH[1]}"
    target_dir="/home/william/GoogleDrive/Sermons/$year"
    
    # Create target directory if it doesn't exist
    mkdir -p "$target_dir"
    
    # Rsync and remove source file
    log "📂 Archiving '$filename' to $target_dir"
    "$RSYNC_BIN" -av --remove-source-files "$file" "$target_dir/"
  else
    log "⚠️ Could not extract year from filename: $filename"
  fi
done

log "🧹 Cleaning up logs older than 30 days..."
find "$LOG_DIR" -type f -name "sermon_pipeline_*.log" -mtime +30 -exec rm {} \;
log "🧼 Log cleanup complete."

log "▶️ Running Archive YouTube Live Videos..."
"$PYTHON_BIN" archive-youtube-live-videos.py --min-days 14

log "✅ All done!"
