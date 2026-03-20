#!/usr/bin/env python3
"""
Endchan Auto-Uploader for MuscleLove AI Art
Posts muscle girl AI art to Endchan imageboards via Lynxchan API.
No account needed - anonymous posting with image + text.
"""

import os
import sys
import json
import time
import re
import random
import glob
import tempfile
import shutil
import requests
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GDRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID_ENDCHAN", "")
ENDCHAN_BOARD = os.environ.get("ENDCHAN_BOARD", "musclelove")

ENDCHAN_POST_URL = "https://endchan.net/newThread.js"
POST_PASSWORD = os.environ.get("ENDCHAN_PASSWORD", "musclelove123")

UPLOAD_LOG = Path(__file__).parent / "uploaded_endchan.json"
IMAGE_DIR = Path(__file__).parent / "images"

PATREON_LINK = "https://www.patreon.com/cw/MuscleLove"

RATE_LIMIT_SECONDS = 65  # wait between posts

# Subjects / descriptions rotated randomly
SUBJECTS = [
    "Muscular Women AI Art - MuscleLove",
    "AI Muscle Girl Collection - MuscleLove",
    "Female Muscle Art - MuscleLove",
    "Strong Women AI Gallery - MuscleLove",
    "Fitness Goddess AI Art - MuscleLove",
    "Powerful Women AI Illustration - MuscleLove",
    "Muscle Beauty AI Art - MuscleLove",
    "Athletic Women AI Creation - MuscleLove",
]

DESCRIPTIONS = [
    "Stunning AI-generated artwork of powerful muscular women. Celebrating female strength and beauty.",
    "Beautiful and strong - AI art showcasing the beauty of muscular women. Female power at its finest.",
    "AI-crafted muscle girl art. Strength is beautiful - celebrating fit and powerful women.",
    "Breathtaking AI illustration of a muscular goddess. Female bodybuilding meets digital art.",
    "Where strength meets beauty - AI generated art of amazing muscular women.",
    "Powerful physiques, stunning aesthetics. AI art celebrating muscular female beauty.",
    "Digital art masterpiece featuring a strong, muscular woman. AI-generated fitness art.",
    "The art of female muscle - AI created illustration of powerful athletic women.",
]

HASHTAGS = "#musclegirl #fitness #AIart #femalemuscle #musclewomen #bodybuilding #strongwomen"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_upload_log() -> list:
    """Load the upload log JSON file."""
    if UPLOAD_LOG.exists():
        with open(UPLOAD_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_upload_log(log: list):
    """Save the upload log JSON file."""
    with open(UPLOAD_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def download_images_from_gdrive(folder_id: str, dest: Path) -> list:
    """Download images from a Google Drive folder using gdown."""
    import gdown

    dest.mkdir(parents=True, exist_ok=True)

    url = f"https://drive.google.com/drive/folders/{folder_id}"
    print(f"[*] Downloading images from Google Drive: {url}")

    try:
        gdown.download_folder(url=url, output=str(dest), quiet=False, use_cookies=False, remaining_ok=True)
    except Exception as e:
        print(f"[!] Download error: {e}")
        # 一部ファイルが失敗しても、ダウンロード済みファイルを使う

    extensions = ("*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp")
    files = []
    for ext in extensions:
        files.extend(dest.glob(ext))
        files.extend(dest.glob(ext.upper()))
    return sorted(files)


def pick_random_image(images: list, uploaded: list) -> Path | None:
    """Pick a random image that hasn't been uploaded yet."""
    uploaded_names = {entry.get("filename") for entry in uploaded}
    available = [img for img in images if img.name not in uploaded_names]

    if not available:
        print("[!] All images have been uploaded. Resetting log for rotation.")
        return random.choice(images) if images else None

    return random.choice(available)


def build_message() -> tuple[str, str]:
    """Build a random subject and message body."""
    subject = random.choice(SUBJECTS)
    description = random.choice(DESCRIPTIONS)

    message = f"""{description}

{HASHTAGS}

More exclusive content: {PATREON_LINK}"""

    return subject, message


def clean_filename(filepath: Path) -> Path:
    """
    Return a copy of the file with a clean filename (no spaces or special chars).
    If the filename is already clean, return the original path.
    """
    clean_name = re.sub(r"[^\w\-.]", "_", filepath.name)
    clean_name = re.sub(r"_+", "_", clean_name)  # collapse multiple underscores
    if clean_name == filepath.name:
        return filepath
    # Copy to temp location with clean name
    tmp_dir = Path(tempfile.mkdtemp())
    clean_path = tmp_dir / clean_name
    shutil.copy2(filepath, clean_path)
    print(f"[*] Cleaned filename: {filepath.name} -> {clean_name}")
    return clean_path


def post_new_thread(board: str, subject: str, message: str,
                    image_path: Path) -> dict:
    """
    Create a new thread on Endchan /musclelove/ via Lynxchan API.
    Own board - no CAPTCHA required.
    POST multipart/form-data to https://endchan.net/newThread.js
    """
    url = ENDCHAN_POST_URL

    # Clean the filename (no spaces or special chars)
    clean_image = clean_filename(image_path)

    # Determine MIME type
    suffix = clean_image.suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    mime = mime_map.get(suffix, "application/octet-stream")

    with open(clean_image, "rb") as img_file:
        files = {
            "files": (clean_image.name, img_file, mime),
        }
        data = {
            "boardUri": board,
            "subject": subject,
            "message": message,
            "password": POST_PASSWORD,
        }

        print(f"[*] Posting new thread to /{board}/ (no CAPTCHA) ...")
        print(f"    URL: {url}")
        print(f"    Subject: {subject}")
        print(f"    Image: {clean_image.name}")

        resp = requests.post(url, data=data, files=files, timeout=60)

    # Clean up temp file if we created one
    if clean_image != image_path:
        clean_image.unlink(missing_ok=True)
        clean_image.parent.rmdir()

    return {
        "status_code": resp.status_code,
        "response": resp.text,
        "url": url,
    }


def post_reply(board: str, thread_id: str, message: str,
               image_path: Path) -> dict:
    """Reply to an existing thread on Endchan."""
    url = "https://endchan.net/replyThread.js"

    clean_image = clean_filename(image_path)

    suffix = clean_image.suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    mime = mime_map.get(suffix, "application/octet-stream")

    with open(clean_image, "rb") as img_file:
        files = {
            "files": (clean_image.name, img_file, mime),
        }
        data = {
            "boardUri": board,
            "threadId": thread_id,
            "message": message,
            "password": POST_PASSWORD,
        }

        print(f"[*] Replying to thread #{thread_id} on /{board}/ ...")
        resp = requests.post(url, data=data, files=files, timeout=60)

    if clean_image != image_path:
        clean_image.unlink(missing_ok=True)
        clean_image.parent.rmdir()

    return {
        "status_code": resp.status_code,
        "response": resp.text,
        "url": url,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  Endchan Auto-Uploader - MuscleLove")
    print(f"  Board: /{ENDCHAN_BOARD}/  (no CAPTCHA)")
    print(f"  {datetime.now().isoformat()}")
    print("=" * 60)

    # 1. Get images from Google Drive
    if GDRIVE_FOLDER_ID:
        images = download_images_from_gdrive(GDRIVE_FOLDER_ID, IMAGE_DIR)
    else:
        print("[!] No GDRIVE_FOLDER_ID_ENDCHAN set. Looking for local images...")
        extensions = ("*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp")
        images = []
        for ext in extensions:
            images.extend(IMAGE_DIR.glob(ext))
            images.extend(IMAGE_DIR.glob(ext.upper()))
        images = sorted(images)

    if not images:
        print("[ERROR] No images found. Aborting.")
        sys.exit(1)

    print(f"[+] Found {len(images)} images")

    # 3. Pick an image
    uploaded_log = load_upload_log()
    image = pick_random_image(images, uploaded_log)
    if not image:
        print("[ERROR] No image selected. Aborting.")
        sys.exit(1)

    print(f"[+] Selected image: {image.name}")

    # 4. Build post content
    subject, message = build_message()

    # 5. Post to Endchan (no CAPTCHA on own board)
    result = post_new_thread(ENDCHAN_BOARD, subject, message, image)

    print(f"\n[*] Response status: {result['status_code']}")
    print(f"[*] Response body: {result['response'][:500]}")

    # 6. Log result
    log_entry = {
        "filename": image.name,
        "board": ENDCHAN_BOARD,
        "subject": subject,
        "post_url": ENDCHAN_POST_URL,
        "status_code": result["status_code"],
        "response": result["response"][:300],
        "posted_at": datetime.now().isoformat(),
    }

    # Check for "Thread created" in response to confirm success
    resp_text = result["response"].lower()
    if "thread created" in resp_text or result["status_code"] == 200:
        log_entry["success"] = True
        print("[+] Thread created successfully!")
    else:
        log_entry["success"] = False
        print(f"[-] Post may have failed. Status: {result['status_code']}")

    uploaded_log.append(log_entry)
    save_upload_log(uploaded_log)
    print(f"[+] Log saved to {UPLOAD_LOG}")

    print("\n[DONE]")


if __name__ == "__main__":
    main()
