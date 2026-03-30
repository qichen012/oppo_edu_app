"""End-to-end-ish API smoke test for Elite Ideas + T2I.

Goal
- Trigger Elite Ideas generation THROUGH your FastAPI endpoints (HTTP), and verify:
  - elite ideas JSON is persisted under data/elite_ideas
  - 2 elite_idea_cards exist
  - each card has image_path
  - image files exist on disk
  - images are exactly 1080x480 (if Pillow is available)

Why it's "most realistic" in this repo
- There is currently no endpoint to upload a handout JSON directly.
    So we either:
    A) Use your real existing handout file (recommended, most realistic)
    B) Or create a small local handout fixture, then call the real API

    In both cases we trigger the real API:
    POST /extract_elite_ideas (form-data) -> generates Elite Ideas + images.

Prereqs
- Start server (default port used previously: 8001)
  python -m run.server
- Ensure T2I is enabled on the server and key is configured:
  export GEMINI_API_KEY="<your zhizengzeng key>"  # or ZHIZENGZENG_GEMINI_API_KEY
  unset ELITE_IDEAS_DISABLE_T2I
- (Optional) disable LLM on server if you only want to test T2I plumbing:
  export ELITE_IDEAS_DISABLE_LLM=1

Run
  python test/test_elite_ideas_full_flow_api.py

Options (env)
- API_BASE_URL: default http://127.0.0.1:8001
- ELITE_IDEAS_T2I_OUT_SIZE: default 1080x480
- ELITE_IDEAS_T2I_TERM1 / TERM2: override two concepts for images
- HANDOUT_FILENAME: use an existing file under data/handouts (e.g. upload_handout.json)
- HANDOUT_PATH: use an existing absolute path to a handout json
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

import requests


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
HANDOUT_DIR = os.path.join(DATA_DIR, "handouts")
ELITE_IDEAS_DIR = os.path.join(DATA_DIR, "elite_ideas")


def _write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


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


def main() -> int:
    base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")

    term1 = os.getenv("ELITE_IDEAS_T2I_TERM1", "费曼学习法")
    term2 = os.getenv("ELITE_IDEAS_T2I_TERM2", "刻意练习")
    out_size = os.getenv("ELITE_IDEAS_T2I_OUT_SIZE", "1080x480")

    # Use your real handout if provided (recommended)
    handout_path_env = str(os.getenv("HANDOUT_PATH", "") or "").strip()
    handout_filename_env = str(os.getenv("HANDOUT_FILENAME", "") or "").strip()

    test_id = f"api_flow_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    if handout_path_env:
        handout_path = handout_path_env
        handout_filename = handout_path_env  # server supports absolute handout_filename
        if not os.path.exists(handout_path):
            print("FAILED: HANDOUT_PATH not found:", handout_path)
            return 10
        print("Using real handout via HANDOUT_PATH")
    elif handout_filename_env:
        handout_filename = handout_filename_env
        handout_path = os.path.join(HANDOUT_DIR, os.path.basename(handout_filename_env))
        if not os.path.exists(handout_path):
            print("FAILED: HANDOUT_FILENAME not found under data/handouts:", handout_path)
            return 11
        print("Using real handout via HANDOUT_FILENAME")
    else:
        # Fixture handout: small but enough for offline fallback and for mapping -> meta_idea_name.
        handout_filename = f"{test_id}_handout.json"
        handout_path = os.path.join(HANDOUT_DIR, handout_filename)

        handout_payload: dict[str, Any] = {
            "meta": {
                "title": "Elite Ideas 全流程 API 测试",
                "subject": "学习方法",
                "source_file": "api_flow_test.pdf",
            },
            "overview": "用于测试 /extract_elite_ideas 与文生图是否全通。",
            "sections": [
                {
                    "title": "学习策略",
                    "content": "本节用于触发 Elite Ideas 与配图生成。",
                    "key_concepts": [
                        {
                            "term": term1,
                            "definition": "用通俗语言讲清楚，发现并填补理解漏洞。",
                            "formula": "",
                            "example": "把概念讲给 12 岁小朋友听。",
                        },
                        {
                            "term": term2,
                            "definition": "在反馈闭环里做高强度、目标明确的练习。",
                            "formula": "",
                            "example": "针对薄弱点做分解训练并复盘。",
                        },
                    ],
                }
            ],
            "summary": "测试产物可后续清理。",
        }

        _write_json(handout_path, handout_payload)
        print("Using generated fixture handout")

    print("API_BASE_URL:", base_url)
    print("handout_path:", handout_path)
    print("expected out size:", out_size)

    # Trigger generation via API
    url = f"{base_url}/extract_elite_ideas"

    # Avoid proxy env vars breaking localhost calls (common in corp networks)
    session = requests.Session()
    session.trust_env = False

    resp = session.post(
        url,
        data={
            "handout_filename": handout_filename,
            "force_regen": "true",
        },
        timeout=600,
    )

    if resp.status_code != 204:
        print("FAILED: POST /extract_elite_ideas")
        print("status:", resp.status_code)
        try:
            print("body:", resp.json())
        except Exception:
            print("body_text:", resp.text[:2000])
        return 1

    # Verify latest elite ideas through API
    get_url = f"{base_url}/get_elite_ideas"
    items = session.get(get_url, timeout=60).json()
    if not isinstance(items, list):
        print("FAILED: GET /get_elite_ideas returned non-list")
        print("json:", items)
        return 2

    # Try to locate output json
    expected_json = os.path.join(ELITE_IDEAS_DIR, f"{test_id}_elite_ideas_db.json")
    if not os.path.exists(expected_json):
        # If we used a real handout, the output file base_name is derived from handout file name
        base_stem = os.path.splitext(os.path.basename(handout_path))[0]
        if base_stem.endswith("_handout"):
            base_stem = base_stem[: -len("_handout")]
        candidate = os.path.join(ELITE_IDEAS_DIR, f"{base_stem}_elite_ideas_db.json")
        if os.path.exists(candidate):
            expected_json = candidate
        else:
            print("FAILED: elite ideas json not found on disk")
            print("tried:", expected_json)
            print("also tried:", candidate)
            print("Tip: check server logs for [extract_elite_ideas] out_json=...")
            return 3

    payload = json.loads(open(expected_json, "r", encoding="utf-8").read())
    cards = payload.get("elite_idea_cards") if isinstance(payload, dict) else None
    if not isinstance(cards, list) or len(cards) != 2:
        print("FAILED: expected 2 elite_idea_cards")
        print("cards:", cards)
        return 4

    # Size parse
    try:
        w_s, h_s = out_size.lower().split("x", 1)
        expected_wh = (int(w_s), int(h_s))
    except Exception:
        expected_wh = (1080, 480)

    ok = True
    for i, c in enumerate(cards, start=1):
        if not isinstance(c, dict):
            ok = False
            continue
        name = c.get("meta_idea_name")
        img_rel = str(c.get("image_path", "") or "").strip()
        print(f"card{i}.meta_idea_name:", name)
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
        print("\nFAILED: Elite Ideas flow not fully OK")
        print("Common causes:")
        print("- T2I disabled on server: ELITE_IDEAS_DISABLE_T2I=1")
        print("- Missing key on server: GEMINI_API_KEY / ZHIZENGZENG_GEMINI_API_KEY")
        print("- Missing Pillow in server env (needed for 1080x480 post-process)")
        return 5

    print("\nOK: Elite Ideas API flow passed")
    print("elite_ideas_json:", expected_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
