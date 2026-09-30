import csv
from datetime import datetime, timedelta, timezone
import os
import re
from telethon import TelegramClient, events

# ==================== CONFIGURATION ====================
from API import (
    API_HASH,
    API_ID,
    BASE_DIR,
    CHANNEL_TARGET,
    MAX_BACKLOG_DAYS,
    MAX_FILE_SIZE_MB,
    MAX_MESSAGE_LIMIT,
)

# Storage paths
MEDIA_DIR = os.path.join(BASE_DIR, "media")
OUTPUT_TXT = os.path.join(BASE_DIR, "telegram_dissemination.txt")
OUTPUT_CSV = os.path.join(BASE_DIR, "dissemination_parsed.csv")

# =======================================================

# Regex pattern for parsing BMKG dissemination message contents
CONTENT_PATTERN = re.compile(
    r"Info Gempa Mag:(?P<magnitude>[\d.]+),\s*"
    r"(?P<event_time>[^,]+),\s*"
    r"Lok:\s*(?P<lat>[\d.]+\s*(?:LS|LU))\s*-\s*(?P<lon>[\d.]+\s*(?:BT|BB))\s*"
    r"\((?P<location>[^)]+)\),\s*"
    r"Kedlmn:\s*(?P<depth>\d+\s*km)"
    r"(?:\s*::(?P<source>\w+))?",
    re.IGNORECASE,
)

CSV_FIELDNAMES = [
    "id",
    "log_time",
    "media_path",
    "magnitude",
    "event_time",
    "latitude",
    "longitude",
    "location_description",
    "depth",
    "source",
]

os.makedirs(MEDIA_DIR, exist_ok=True)

# Initialize CSV header if the file does not exist yet
if not os.path.exists(OUTPUT_CSV):
  with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
    writer.writeheader()

# Initialize client with 24/7 auto-reconnect capability
client = TelegramClient(
    "dissemination_session",
    API_ID,
    API_HASH,
    connection_retries=None,
    retry_delay=5,
    auto_reconnect=True,
)


def check_media_size(message):
  """Verify media size before downloading to protect storage capacity."""
  if hasattr(message, "file") and message.file and message.file.size:
    return message.file.size <= (MAX_FILE_SIZE_MB * 1024 * 1024)
  return True


def save_to_csv(msg_id, msg_date, media_path, caption_text):
  """Parse parameters from caption and append a structured row to CSV."""
  match = CONTENT_PATTERN.search(caption_text) if caption_text else None

  if match:
    data = match.groupdict()
    row = {
        "id": msg_id,
        "log_time": str(msg_date),
        "media_path": media_path,
        "magnitude": data.get("magnitude", ""),
        "event_time": data.get("event_time", ""),
        "latitude": data.get("lat", ""),
        "longitude": data.get("lon", ""),
        "location_description": data.get("location", ""),
        "depth": data.get("depth", ""),
        "source": data.get("source") or "BMKG",
    }
  else:
    # Fallback if the message structure deviates from standard BMKG formatting
    row = {
        "id": msg_id,
        "log_time": str(msg_date),
        "media_path": media_path,
        "magnitude": "",
        "event_time": "",
        "latitude": "",
        "longitude": "",
        "location_description": caption_text,
        "depth": "",
        "source": "",
    }

  with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
    writer.writerow(row)


async def process_and_save(message, log_prefix="[REALTIME]"):
  """Process a single message: download media, append raw TXT, and write parsed CSV."""
  caption_text = message.message if message.message else ""
  media_status = "No media"

  # Handle media download (photos, infographic images, or animations/GIFs)
  if message.media:
    if check_media_size(message):
      base_filename = os.path.join(MEDIA_DIR, f"media_{message.id}")

      # Check if file was already downloaded
      existing_files = [
          f for f in os.listdir(MEDIA_DIR) if f.startswith(f"media_{message.id}")
      ]

      if not existing_files:
        downloaded_path = await client.download_media(
            message.media, file=base_filename
        )
        if downloaded_path:
          media_status = downloaded_path
          print(
              f"{log_prefix} Media saved:"
              f" {os.path.basename(downloaded_path)}"
          )
      else:
        media_status = os.path.join(MEDIA_DIR, existing_files[0])
    else:
      media_status = f"[Skipped: File size exceeds {MAX_FILE_SIZE_MB}MB]"

  # 1. Append raw record to output TXT file
  if caption_text or message.media:
    with open(OUTPUT_TXT, "a", encoding="utf-8") as f:
      f.write(f"[{message.date}] - ID: {message.id}\n")
      f.write(f"Media  : {media_status}\n")
      f.write(f"Content: {caption_text}\n")
      f.write("-" * 50 + "\n")

    # 2. Append parsed structured parameters to CSV
    save_to_csv(message.id, message.date, media_status, caption_text)
    print(
        f"{log_prefix} Appended ID {message.id} to"
        f" {os.path.basename(OUTPUT_CSV)}"
    )


async def sync_initial_history():
  """Fetch message backlog up to 30 days within storage constraints."""
  cutoff_date = datetime.now(timezone.utc) - timedelta(days=MAX_BACKLOG_DAYS)
  print(
      f"[*] Starting history sync from: {cutoff_date.strftime('%Y-%m-%d')}..."
  )

  message_backlog = []
  async for msg in client.iter_messages(
      CHANNEL_TARGET, limit=MAX_MESSAGE_LIMIT
  ):
    if msg.date < cutoff_date:
      break
    message_backlog.append(msg)

  # Reverse to maintain chronological order (oldest to newest)
  message_backlog.reverse()
  print(f"[*] Found {len(message_backlog)} messages within the last 30 days.")

  for msg in message_backlog:
    await process_and_save(msg, log_prefix="[BACKLOG]")

  print("[*] Initial sync completed. Media, logs, and CSV are up to date.\n")


@client.on(events.NewMessage(chats=CHANNEL_TARGET))
async def handle_new_message(event):
  """Listen for incoming messages and process them immediately."""
  print(f"\n[!] New message received at {event.message.date}")
  await process_and_save(event.message, log_prefix="[REALTIME]")


async def main():
  # 1. Synchronize backlog data
  await sync_initial_history()

  # 2. Transition into persistent real-time listener
  print(
      f"[*] System standby: monitoring channel @{CHANNEL_TARGET} in"
      " real-time..."
  )
  await client.run_until_disconnected()


with client:
  client.loop.run_until_complete(main())