"""API smoke test for SparkLink brief generation.

Goal
- Call FastAPI endpoint POST /generate_sparklink_brief
- date_a: pick extracurricular knowledge from screenshot analysis records
- date_b: pick in-class knowledge from all daily briefs of that day

Prereqs
- Start server:
  python -m run.server

Run (mock mode, no LLM calls)
  python test/test_sparklink_brief_api.py

Env
- API_BASE_URL: default http://127.0.0.1:8001
- DATE_A / DATE_B: override test dates
- USER_ID: output file naming only (default 0)
"""

from __future__ import annotations

import json
import os

import requests


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main() -> int:
    base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
    date_a = os.getenv("DATE_A", "2026-03-09")
    date_b = os.getenv("DATE_B", "2026-03-12")
    user_id = int(os.getenv("USER_ID", "0"))

    session = requests.Session()
    session.trust_env = False

    url = f"{base_url}/generate_sparklink_brief"
    resp = session.post(
        url,
        json={
            "date_a": date_a,
            "date_b": date_b,
            "user_id": user_id,
            "mock": True,
            "save_to_file": True,
            "force_regen": False,
        },
        timeout=600,
    )

    if resp.status_code != 200:
        print("FAILED: POST /generate_sparklink_brief")
        print("status:", resp.status_code)
        try:
            print("body:", resp.json())
        except Exception:
            print("body_text:", resp.text[:2000])
        return 1

    payload = resp.json()
    if not isinstance(payload, dict):
        print("FAILED: response is not a dict")
        print("json:", payload)
        return 2

    required = ["posterior_insight", "key_concepts"]
    for k in required:
        if k not in payload:
            print("FAILED: missing key:", k)
            print("keys:", list(payload.keys()))
            return 3

    # 仍然验证落盘是否存在（接口不返回路径，因此按约定路径推导）
    rel_path = os.path.join(
        "data",
        "daily_briefs",
        f"sparklink_brief_{date_a}_{date_b}_user{user_id}.json",
    )
    abs_path = os.path.join(PROJECT_ROOT, rel_path)
    if not os.path.exists(abs_path):
        print("FAILED: archived file not found on disk")
        print("expected_rel:", rel_path)
        print("abs_path:", abs_path)
        return 4

    try:
        disk = json.loads(open(abs_path, "r", encoding="utf-8").read())
        if not isinstance(disk, dict):
            raise ValueError("not a dict")
    except Exception as e:
        print("FAILED: failed to read archived file")
        print("error:", e)
        return 5

    print("OK: SparkLink API flow passed")
    print("archived_at:", rel_path)
    print("posterior_insight_preview:", str(payload.get("posterior_insight", ""))[:80].replace("\n", " ") + "...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
