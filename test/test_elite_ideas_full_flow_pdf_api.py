"""Full flow API test: upload PDF -> generate handout -> elite ideas -> images.

This is the most realistic simulation of the app flow:
1) POST /generate_handout with a real PDF
2) Detect the newly created handout file under data/handouts
3) Wait until corresponding elite ideas JSON is persisted under data/elite_ideas
4) Verify 2 cards, each with image_path, image exists on disk, and size is 1080x480

Prereqs
- Start server:
    python -m run.server
- Configure T2I on the SERVER side (environment where server runs):
    export GEMINI_API_KEY="<your zhizengzeng key>"  # or ZHIZENGZENG_GEMINI_API_KEY
    unset ELITE_IDEAS_DISABLE_T2I

Run
    python test/test_elite_ideas_full_flow_pdf_api.py

Env options
- API_BASE_URL: default http://127.0.0.1:8001
- PDF_PATH: default data/test/test01.pdf
- TIMEOUT_SECS: default 180
"""

from __future__ import annotations

import os
import time
from typing import Optional

import requests


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
HANDOUT_DIR = os.path.join(DATA_DIR, "handouts")
ELITE_IDEAS_DIR = os.path.join(DATA_DIR, "elite_ideas")


def _try_check_image_size(abs_path: str, expected: tuple[int, int]) -> tuple[bool, str]:
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return True, "Pillow not available; skipped size check"

    try:
        with Image.open(abs_path) as im:
            if im.size != expected:
                return False, f"unexpected size {im.size}, expected {expected}"
    except Exception as e:
        return False, f"failed to open image: {e}"

    return True, "size ok"


def _latest_handout_mtime() -> float:
    if not os.path.isdir(HANDOUT_DIR):
        return 0.0
    candidates = [
        os.path.join(HANDOUT_DIR, fn)
        for fn in os.listdir(HANDOUT_DIR)
        if fn.endswith("_handout.json")
    ]
    if not candidates:
        return 0.0
    return max(os.path.getmtime(p) for p in candidates)


def _find_new_handout(after_mtime: float, *, timeout: float) -> Optional[str]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not os.path.isdir(HANDOUT_DIR):
            time.sleep(0.5)
            continue

        candidates = [
            os.path.join(HANDOUT_DIR, fn)
            for fn in os.listdir(HANDOUT_DIR)
            if fn.endswith("_handout.json")
        ]
        if candidates:
            newest = max(candidates, key=os.path.getmtime)
            if os.path.getmtime(newest) > after_mtime:
                return newest
        time.sleep(0.5)

    return None


def _base_name_from_handout_path(handout_path: str) -> str:
    stem = os.path.splitext(os.path.basename(handout_path))[0]
    if stem.endswith("_handout"):
        stem = stem[: -len("_handout")]
    return stem


def main() -> int:
    base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
    pdf_path = os.getenv("PDF_PATH", os.path.join("data", "test", "test01.pdf"))
    timeout_secs = int(os.getenv("TIMEOUT_SECS", "180"))

    # Resolve PDF path
    if not os.path.isabs(pdf_path):
        pdf_path = os.path.join(PROJECT_ROOT, pdf_path)

    if not os.path.exists(pdf_path):
        print("FAILED: PDF not found:", pdf_path)
        return 10

    print("API_BASE_URL:", base_url)
    print("PDF_PATH:", pdf_path)

    before_mtime = _latest_handout_mtime()

    # Call API (avoid proxy env breaking localhost)
    session = requests.Session()
    session.trust_env = False

    url = f"{base_url}/generate_handout"
    with open(pdf_path, "rb") as f:
        files = {"file": (os.path.basename(pdf_path), f, "application/pdf")}
        resp = session.post(url, files=files, timeout=600)

    if resp.status_code != 204:
        print("FAILED: POST /generate_handout")
        print("status:", resp.status_code)
        print("body:", resp.text[:2000])
        return 1

    # Find new handout written by server
    handout_path = _find_new_handout(before_mtime, timeout=timeout_secs)
    if not handout_path:
        print("FAILED: did not detect new handout file under data/handouts within timeout")
        print("Tip: check server logs and whether handout generation succeeded")
        return 2

    print("handout_path:", handout_path)

    base_name = _base_name_from_handout_path(handout_path)
    elite_json = os.path.join(ELITE_IDEAS_DIR, f"{base_name}_elite_ideas_db.json")

    # Wait elite ideas (background task)
    deadline = time.time() + timeout_secs
    while time.time() < deadline and not os.path.exists(elite_json):
        time.sleep(0.5)

    if not os.path.exists(elite_json):
        print("FAILED: elite ideas json not found within timeout")
        print("expected:", elite_json)
        print("Tip: ensure T2I/LLM keys configured on SERVER; check [auto_elite_ideas] logs")
        return 3

    # Load and validate
    import json

    payload = json.loads(open(elite_json, "r", encoding="utf-8").read())
    cards = payload.get("elite_idea_cards") if isinstance(payload, dict) else None
    if not isinstance(cards, list) or len(cards) != 2:
        print("FAILED: expected 2 elite_idea_cards")
        print("cards:", cards)
        return 4

    expected_wh = (1080, 480)
    ok = True
    for i, c in enumerate(cards, start=1):
        if not isinstance(c, dict):
            ok = False
            continue
        print(f"card{i}.meta_idea_name:", c.get("meta_idea_name"))
        img_rel = str(c.get("image_path", "") or "").strip()
        print(f"card{i}.image_path:", img_rel)

        if not img_rel:
            ok = False
            print("  MISSING image_path (T2I likely disabled or failed)")
            continue

        abs_img = os.path.join(PROJECT_ROOT, img_rel.replace("/", os.sep))
        if not os.path.exists(abs_img):
            ok = False
            print("  image missing on disk:", abs_img)
            continue

        size_ok, msg = _try_check_image_size(abs_img, expected_wh)
        if not size_ok:
            ok = False
        print("  size_check:", msg)

    if not ok:
        print("\nFAILED: flow completed but images missing/invalid")
        return 5

    print("\nOK: PDF -> handout -> elite ideas -> images full flow passed")
    print("elite_ideas_json:", elite_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
