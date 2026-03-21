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
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
ENDCHAN_BOARD = os.environ.get("ENDCHAN_BOARD", "musclelove")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

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
    "Thick & Muscular Goddess - MuscleLove 💪",
    "Dark Skin Muscle Beauty - MuscleLove 🔥",
    "Voluptuous Fit Girl AI Art - MuscleLove",
    "Toned & Powerful Women - MuscleLove ✨",
    "Muscle Worship AI Collection - MuscleLove",
    "Thicc Fit Goddess AI Art - MuscleLove",
    "Armpit & Muscle Definition - MuscleLove",
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
    "Thick, muscular, and absolutely gorgeous. Dark skin muscle beauty at its finest.",
    "Voluptuous and powerful - the ultimate combo of strength and curves.",
    "Trained bodies are the fetish. Thick muscular women with incredible definition.",
    "Muscle worship material - toned arms, defined abs, powerful physique.",
    "Fit, thick, and built different. AI-generated muscle goddess art.",
    "Dark skin glow meets muscle definition. Breathtaking AI fitness art.",
    "Armpit and muscle definition showcase. Celebrating every angle of the fit female form.",
]

HASHTAGS = "#musclegirl #fitness #AIart #femalemuscle #musclewomen #bodybuilding #strongwomen #musclebeauty #thicc #thickfit #armpitfetish #tonedbody #fitchick #muscleworship"

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


def _list_via_api(folder_id: str) -> list:
    """Google Drive API v3で画像一覧を取得（サブフォルダ再帰）"""
    url = "https://www.googleapis.com/drive/v3/files"
    images = []

    def _list_page(parent_id: str):
        query = f"'{parent_id}' in parents and trashed = false"
        params = {
            "q": query,
            "key": GOOGLE_API_KEY,
            "fields": "files(id,name,mimeType)",
            "pageSize": 1000,
        }
        resp = requests.get(url, params=params, timeout=60)
        resp.raise_for_status()
        for f in resp.json().get("files", []):
            mime = (f.get("mimeType") or "").lower()
            ext = Path(f["name"]).suffix.lower()
            if "folder" in mime:
                _list_page(f["id"])
            elif ext in IMAGE_EXTENSIONS:
                images.append({"id": f["id"], "name": f["name"]})

    _list_page(folder_id)
    return images


def _list_via_gdown(folder_id: str, dest: Path) -> list:
    """gdownでフォルダをダウンロード（APIキー不要）"""
    import gdown
    dest.mkdir(parents=True, exist_ok=True)
    url = f"https://drive.google.com/drive/folders/{folder_id}"
    print(f"[*] Downloading from Google Drive (gdown): {url}")
    try:
        gdown.download_folder(url=url, output=str(dest), quiet=False, use_cookies=False, remaining_ok=True)
    except Exception as e:
        print(f"[!] Download error: {e}")

    files = []
    for ext in IMAGE_EXTENSIONS:
        files.extend(dest.rglob(f"*{ext}"))
        files.extend(dest.rglob(f"*{ext.upper()}"))
    return [{"id": None, "name": p.name, "local_path": p} for p in sorted(set(files))]


def _download_single_api(file_id: str, dest: Path, filename: str) -> Path:
    """Google Drive APIで1ファイルをダウンロード"""
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
    resp = requests.get(url, params={"alt": "media", "key": GOOGLE_API_KEY}, timeout=120)
    resp.raise_for_status()
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / filename
    out.write_bytes(resp.content)
    return out


def list_gdrive_images(folder_id: str, dest: Path) -> list:
    """Google Drive API（優先）またはgdownで画像一覧を取得"""
    if GOOGLE_API_KEY:
        print("[*] Using Google Drive API")
        try:
            return _list_via_api(folder_id)
        except Exception as e:
            print(f"[!] Google Drive API failed: {e}")
            print("[*] Falling back to gdown...")
    return _list_via_gdown(folder_id, dest)


def pick_random_image(images: list, uploaded: list) -> dict | None:
    """Pick a random image that hasn't been uploaded yet."""
    uploaded_names = {entry.get("filename") for entry in uploaded}
    name_getter = lambda x: x["name"] if isinstance(x, dict) else x.name
    available = [img for img in images if name_getter(img) not in uploaded_names]

    if not available:
        print("[!] All images have been uploaded. Resetting log for rotation.")
        return random.choice(images) if images else None

    return random.choice(available)


def ensure_local_path(item: dict, dest: Path) -> Path:
    """Return local file path, downloading via API if needed."""
    if item.get("local_path"):
        p = Path(item["local_path"])
        if p.exists():
            return p
    if item.get("id") and GOOGLE_API_KEY:
        return _download_single_api(item["id"], dest, item["name"])
    raise ValueError("No way to get file: missing local_path and (id+API key)")


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
        images = list_gdrive_images(GDRIVE_FOLDER_ID, IMAGE_DIR)
    else:
        print("[!] No GDRIVE_FOLDER_ID_ENDCHAN set. Looking for local images...")
        files = []
        for ext in IMAGE_EXTENSIONS:
            files.extend(IMAGE_DIR.glob(f"*{ext}"))
            files.extend(IMAGE_DIR.glob(f"*{ext.upper()}"))
        images = [{"id": None, "name": p.name, "local_path": p} for p in sorted(set(files))]

    if not images:
        print("[ERROR] No images found. Aborting.")
        sys.exit(1)

    print(f"[+] Found {len(images)} images")

    # 2. Pick an image
    uploaded_log = load_upload_log()
    image_item = pick_random_image(images, uploaded_log)
    if not image_item:
        print("[ERROR] No image selected. Aborting.")
        sys.exit(1)

    image = ensure_local_path(image_item, IMAGE_DIR)
    print(f"[+] Selected image: {image.name}")

    # 3. Build post content
    subject, message = build_message()

    # 4. Post to Endchan (no CAPTCHA on own board)
    result = post_new_thread(ENDCHAN_BOARD, subject, message, image)

    print(f"\n[*] Response status: {result['status_code']}")
    print(f"[*] Response body: {result['response'][:500]}")

    # 5. Log result
    log_entry = {
        "filename": image_item["name"],
        "board": ENDCHAN_BOARD,
        "subject": subject,
        "post_url": ENDCHAN_POST_URL,
        "status_code": result["status_code"],
        "response": result["response"][:300],
        "posted_at": datetime.now().isoformat(),
    }

    # Check for success
    resp_text = result["response"].lower()
    if result["status_code"] == 200:
        log_entry["success"] = True
        print("[+] Thread created successfully!")
        uploaded_log.append(log_entry)
        save_upload_log(uploaded_log)
        print(f"[+] Log saved to {UPLOAD_LOG}")
        print("\n[DONE]")
    else:
        log_entry["success"] = False
        print(f"[-] Post failed. Status: {result['status_code']}")
        uploaded_log.append(log_entry)
        save_upload_log(uploaded_log)
        sys.exit(1)


if __name__ == "__main__":
    main()
