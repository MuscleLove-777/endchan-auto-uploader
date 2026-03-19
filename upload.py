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
import random
import glob
import tempfile
import requests
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GDRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID_ENDCHAN", "")
ENDCHAN_BOARD = os.environ.get("ENDCHAN_BOARD", "b")

ENDCHAN_BASES = [
    "https://endchan.org",
    "https://endchan.net",
    "https://endchan.gg",
]

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

    gdown.download_folder(url=url, output=str(dest), quiet=False, use_cookies=False)

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


def find_working_base() -> str | None:
    """Find a working Endchan base URL."""
    for base in ENDCHAN_BASES:
        try:
            resp = requests.get(f"{base}/status", timeout=15)
            if resp.status_code < 500:
                print(f"[+] Using base URL: {base}")
                return base
        except requests.RequestException:
            print(f"[-] {base} unreachable, trying next...")
            continue

    # Fallback: try catalog endpoint
    for base in ENDCHAN_BASES:
        try:
            resp = requests.get(f"{base}/{ENDCHAN_BOARD}/catalog.json", timeout=15)
            if resp.status_code == 200:
                print(f"[+] Using base URL (via catalog): {base}")
                return base
        except requests.RequestException:
            continue

    return None


def check_captcha(base_url: str, board: str) -> tuple[str, str] | None:
    """
    Check if CAPTCHA is required and attempt to fetch it.
    Returns (captchaId, captcha_image_url) or None if not required.
    """
    try:
        resp = requests.get(
            f"{base_url}/captcha.js",
            params={"boardUri": board},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            captcha_id = data.get("captchaId") or data.get("id")
            if captcha_id:
                print(f"[!] CAPTCHA required. ID: {captcha_id}")
                return captcha_id, data
        return None
    except Exception as e:
        print(f"[*] CAPTCHA check error (may not be required): {e}")
        return None


def post_new_thread(base_url: str, board: str, subject: str, message: str,
                    image_path: Path) -> dict:
    """Create a new thread on Endchan via Lynxchan API."""
    url = f"{base_url}/newThread.js"

    # Determine MIME type
    suffix = image_path.suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    mime = mime_map.get(suffix, "application/octet-stream")

    with open(image_path, "rb") as img_file:
        files = {
            "files": (image_path.name, img_file, mime),
        }
        data = {
            "boardUri": board,
            "subject": subject,
            "message": message,
            "noFlag": "true",
        }

        # Check CAPTCHA
        captcha_info = check_captcha(base_url, board)
        if captcha_info:
            captcha_id, captcha_data = captcha_info
            print("[!] CAPTCHA is required for this board.")
            print("[!] Automatic CAPTCHA solving not yet implemented.")
            print("[!] Attempting post without CAPTCHA answer (may fail)...")
            data["captchaId"] = captcha_id
            data["captcha"] = ""

        print(f"[*] Posting new thread to /{board}/ ...")
        print(f"    Subject: {subject}")
        print(f"    Image: {image_path.name}")

        resp = requests.post(url, data=data, files=files, timeout=60)

    return {
        "status_code": resp.status_code,
        "response": resp.text,
        "url": url,
    }


def post_reply(base_url: str, board: str, thread_id: str, message: str,
               image_path: Path) -> dict:
    """Reply to an existing thread on Endchan."""
    url = f"{base_url}/replyThread.js"

    suffix = image_path.suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    mime = mime_map.get(suffix, "application/octet-stream")

    with open(image_path, "rb") as img_file:
        files = {
            "files": (image_path.name, img_file, mime),
        }
        data = {
            "boardUri": board,
            "threadId": thread_id,
            "message": message,
        }

        print(f"[*] Replying to thread #{thread_id} on /{board}/ ...")
        resp = requests.post(url, data=data, files=files, timeout=60)

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
    print(f"  {datetime.now().isoformat()}")
    print("=" * 60)

    # 1. Find working Endchan mirror
    base_url = find_working_base()
    if not base_url:
        print("[ERROR] No reachable Endchan mirror found. Aborting.")
        sys.exit(1)

    # 2. Get images from Google Drive
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

    # 5. Post to Endchan
    result = post_new_thread(base_url, ENDCHAN_BOARD, subject, message, image)

    print(f"\n[*] Response status: {result['status_code']}")
    print(f"[*] Response body: {result['response'][:500]}")

    # 6. Log result
    log_entry = {
        "filename": image.name,
        "board": ENDCHAN_BOARD,
        "subject": subject,
        "base_url": base_url,
        "status_code": result["status_code"],
        "response": result["response"][:300],
        "posted_at": datetime.now().isoformat(),
    }

    # Consider success if status is 200 or response contains thread ID
    if result["status_code"] == 200 or "id" in result["response"].lower():
        log_entry["success"] = True
        print("[+] Post appears successful!")
    else:
        log_entry["success"] = False
        print(f"[-] Post may have failed. Status: {result['status_code']}")

    uploaded_log.append(log_entry)
    save_upload_log(uploaded_log)
    print(f"[+] Log saved to {UPLOAD_LOG}")

    print("\n[DONE]")


if __name__ == "__main__":
    main()
