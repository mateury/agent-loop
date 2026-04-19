"""Telegram file/photo/voice handling."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from telegram import Update

log = logging.getLogger(__name__)

# Media type detection by file extension
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


def detect_media_type(path: str | Path) -> str:
    """Detect media type from file extension. Returns 'photo', 'video', or 'document'."""
    suffix = Path(path).suffix.lower()
    if suffix in PHOTO_EXTENSIONS:
        return "photo"
    elif suffix in VIDEO_EXTENSIONS:
        return "video"
    return "document"


def sanitize_filename(name: str) -> str:
    """Remove special characters from filename."""
    return re.sub(r"[^\w\-.]", "_", name)


async def download_file(update: Update, files_dir: Path) -> tuple[Path, str]:
    """Download a file or photo from a Telegram message.

    Returns:
        Tuple of (local_path, caption/text).
    """
    files_dir.mkdir(parents=True, exist_ok=True)
    msg = update.message
    timestamp = int(time.time())

    if msg.photo:
        # Download highest-resolution photo
        photo = msg.photo[-1]
        file = await photo.get_file()
        filename = f"photo_{timestamp}_{photo.file_unique_id}.jpg"
        local_path = files_dir / filename
        await file.download_to_drive(local_path)
        caption = msg.caption or ""
        return local_path, caption

    elif msg.document:
        doc = msg.document
        file = await doc.get_file()
        safe_name = sanitize_filename(doc.file_name or "document")
        filename = f"{timestamp}_{safe_name}"
        local_path = files_dir / filename
        await file.download_to_drive(local_path)
        caption = msg.caption or ""
        return local_path, caption

    raise ValueError("No downloadable file in message")


async def download_voice(update: Update, files_dir: Path) -> Path:
    """Download a voice message from Telegram.

    Returns:
        Path to the downloaded audio file.
    """
    files_dir.mkdir(parents=True, exist_ok=True)
    msg = update.message
    voice = msg.voice or msg.audio

    if not voice:
        raise ValueError("No voice/audio in message")

    file = await voice.get_file()
    timestamp = int(time.time())
    filename = f"voice_{timestamp}_{voice.file_unique_id}.oga"
    local_path = files_dir / filename
    await file.download_to_drive(local_path)
    return local_path
