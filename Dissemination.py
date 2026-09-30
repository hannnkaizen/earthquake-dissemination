from datetime import datetime, timedelta, timezone
import os
from telethon import TelegramClient, events

# ==================== CONFIGURATION ====================
API_ID = 32622253  # Replace with your API ID
API_HASH = "6a4a73e50d131a6fa42f4589a641db4c"  # Replace with your API Hash
CHANNEL_TARGET = (
    "integrasidata"  # Target channel username (without https://t.me/) or chat ID
)

# Storage paths (adjust according to your system environment)
BASE_DIR = rf"/home/han/GitHub/earthquake-dissemination/"
MEDIA_DIR = os.path.join(BASE_DIR, "media")
OUTPUT_TXT = os.path.join(BASE_DIR, "telegram_dissemination.txt")

# Storage protection constraints
MAX_BACKLOG_DAYS = 30  # Fetch history up to 30 days back
MAX_MESSAGE_LIMIT = 200  # Maximum message count limit during initial sync
MAX_FILE_SIZE_MB = 15  # Skip download if file size exceeds 15 MB
# =======================================================

os.makedirs(MEDIA_DIR, exist_ok=True)

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


async def process_and_save(message, log_prefix="[REALTIME]"):
  """Process a single message: download media and append text to output file."""
  caption_text = message.message if message.message else ""
  media_status = "No media"

  # Handle media download (photos, infographic images, or animations/GIFs)
  if message.media:
    if check_media_size(message):
      base_filename = os.path.join(MEDIA_DIR, f"media_{message.id}")

      # Check if the file was already downloaded
      already_exists = any(
          f.startswith(f"media_{message.id}") for f in os.listdir(MEDIA_DIR)
      )

      if not already_exists:
        downloaded_path = await client.download_media(
            message.media, file=base_filename
        )
        if downloaded_path:
          media_status = downloaded_path
          print(
              f"{log_prefix} Media saved: {os.path.basename(downloaded_path)}"
          )
      else:
        media_status = f"[File media_{message.id} already exists]"
    else:
      media_status = f"[Skipped: File size exceeds {MAX_FILE_SIZE_MB}MB]"

  # Append record to output file
  if caption_text or message.media:
    with open(OUTPUT_TXT, "a", encoding="utf-8") as f:
      f.write(f"[{message.date}] - ID: {message.id}\n")
      f.write(f"Media  : {media_status}\n")
      f.write(f"Content: {caption_text}\n")
      f.write("-" * 50 + "\n")


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

  print("[*] Initial sync completed. Media and logs are up to date.\n")


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