import json
import os
import sys
import time
import uuid
import asyncio


# Ensure project root is importable (so `import run.server` works when executed as a script).
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main() -> int:
    # Force offline mode so the test doesn't depend on any LLM availability.
    os.environ["ELITE_IDEAS_DISABLE_LLM"] = "1"
    # Disable text-to-image in this offline smoke test.
    os.environ["ELITE_IDEAS_DISABLE_T2I"] = "1"

    # Import after env is set (env is read at runtime, but keeping import order explicit is safer).
    from run.server import extract_elite_ideas as api_extract_elite_ideas
    from run.server import api_get_elite_ideas as api_get_elite_ideas
    from skill.elite_ideas_extractor import HANDOUT_DIR, ELITE_IDEAS_OUTPUT_DIR

    base = f"localtest_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    handout_filename = f"{base}_handout.json"
    handout_path = os.path.join(HANDOUT_DIR, handout_filename)

    # Minimal handout schema that _handout_to_text + offline fallback can consume.
    handout_payload = {
        "meta": {
            "title": "本地冒烟测试讲义",
            "subject": "信息论",
            "source_file": "local_smoke_test.pdf",
        },
        "overview": "用于验证 /extract_elite_ideas 是否会落盘到 data/elite_ideas。",
        "sections": [
            {
                "title": "基础概念",
                "content": "本段只用于本地测试。",
                "key_concepts": [
                    {
                        "term": "自信息",
                        "definition": "单个事件发生带来的信息量。",
                        "formula": "I(x)=-log p(x)",
                        "example": "掷硬币正面：p=0.5",
                    },
                    {
                        "term": "联合自信息",
                        "definition": "多个事件同时发生的信息量。",
                        "formula": "I(x,y)=-log p(x,y)",
                        "example": "两次掷硬币同时为正面",
                    },
                ],
            }
        ],
        "summary": "测试结束后可删除产物。",
    }

    _write_json(handout_path, handout_payload)

    out_json_path = os.path.join(ELITE_IDEAS_OUTPUT_DIR, f"{base}_elite_ideas_db.json")
    out_md_path = os.path.join(ELITE_IDEAS_OUTPUT_DIR, f"{base}_elite_ideas.md")

    # Clean up any stale/partial outputs from previous runs.
    for p in (out_json_path, out_md_path):
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

    try:
        resp = asyncio.run(
            api_extract_elite_ideas(
                source_file=None,
                handout_filename=handout_filename,
                daily_brief_id=None,
                force_regen=True,
            )
        )
    except Exception as e:
        print("Direct call to api_extract_elite_ideas() raised")
        print("error:", repr(e))
        return 1

    status_code = getattr(resp, "status_code", None)
    if status_code != 204:
        print("Expected status_code=204")
        print("got:", status_code)
        print("resp:", resp)
        return 1

    if not os.path.exists(out_json_path):
        print("Expected output json not found:", out_json_path)
        print("Note: output directory is 'data/elite_ideas' (elite_ideas, not elit_ideas).")
        return 2

    with open(out_json_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    cards = payload.get("elite_idea_cards") if isinstance(payload, dict) else None
    if not isinstance(cards, list) or len(cards) != 2:
        print("Unexpected elite_idea_cards length; expected 2")
        print("out_json_path:", out_json_path)
        print("elite_idea_cards:", cards)
        return 3

    try:
        items = asyncio.run(api_get_elite_ideas())
    except Exception as e:
        print("Direct call to api_get_elite_ideas() raised")
        print("error:", repr(e))
        return 4
    if not isinstance(items, list):
        print("GET /get_elite_ideas returned non-list JSON")
        print("json:", items)
        return 5

    # Verify our newly generated file shows up.
    found = False
    for item in items:
        if isinstance(item, dict) and str(item.get("archived_at", "")).endswith(f"{base}_elite_ideas_db.json"):
            found = True
            break

    if not found:
        print("Generated elite ideas file not present in GET /get_elite_ideas response")
        print("expected suffix:", f"{base}_elite_ideas_db.json")
        return 6

    print("OK: elite ideas generated and persisted")
    print("handout_path:", handout_path)
    print("out_json_path:", out_json_path)
    print("out_md_path:", out_md_path, "(exists:" + str(os.path.exists(out_md_path)) + ")")

    # Cleanup temporary handout (leave elite ideas outputs for inspection).
    try:
        os.remove(handout_path)
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
