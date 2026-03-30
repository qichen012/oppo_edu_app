"""Manual quality test for Elite Ideas text-to-image.

Run:
  # (recommended) provide key via env
  export GEMINI_API_KEY="..."   # or ZHIZENGZENG_GEMINI_API_KEY

    # output size (default: 1080x480)
    export ELITE_IDEAS_T2I_OUT_SIZE="1080x480"

  # ensure T2I enabled
  unset ELITE_IDEAS_DISABLE_T2I

  python test/test_elite_ideas_t2i_quality.py

What it does:
- Creates a temporary handout JSON under data/handouts
- Runs process_handout_to_elite_ideas(force_regen=True, save_to_file=True)
- Expects 2 elite_idea_cards, each with generated image saved under data/elite_ideas/images
- Prints output json + image paths so you can open them to judge quality
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main() -> int:
    # Keep this test deterministic and cheap: we don't need LLM to judge image quality.
    # The offline fallback will create 2 cards from key_concepts[*].term.
    os.environ.setdefault("ELITE_IDEAS_DISABLE_LLM", "1")

    # Enable T2I explicitly for this test.
    os.environ.pop("ELITE_IDEAS_DISABLE_T2I", None)

    from skill.elite_ideas_extractor import HANDOUT_DIR
    from skill.elite_ideas_extractor import process_handout_to_elite_ideas

    base = f"t2i_quality_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    handout_filename = f"{base}_handout.json"
    handout_path = os.path.join(HANDOUT_DIR, handout_filename)

    # Choose 2 concepts you want to visually inspect.
    # These become meta_idea_name in offline mode.
    term1 = os.getenv("ELITE_IDEAS_T2I_TERM1", "费曼学习法")
    term2 = os.getenv("ELITE_IDEAS_T2I_TERM2", "刻意练习")

    handout_payload = {
        "meta": {
            "title": "Elite Ideas 文生图质量测试",
            "subject": "学习方法",
            "source_file": "t2i_quality_test.pdf",
        },
        "overview": "用于测试 Elite Ideas 的文生图质量（每个 handout 两张图）。",
        "sections": [
            {
                "title": "学习策略",
                "content": "本节只用于触发 Elite Ideas 离线兜底与文生图。",
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
        "summary": "测试完成后可删除产物。",
    }

    _write_json(handout_path, handout_payload)

    print("handout_path:", handout_path)
    print("T2I model:", os.getenv("ELITE_IDEAS_T2I_MODEL", "gemini-2.5-flash-image"))
    print("T2I out size:", os.getenv("ELITE_IDEAS_T2I_OUT_SIZE", "1080x480"))

    result = process_handout_to_elite_ideas(
        handout_filename=handout_filename,
        save_to_file=True,
        force_regen=True,
    )

    if not isinstance(result, dict) or not result.get("success"):
        print("FAILED:", result)
        return 1

    out_json_path = result.get("output_json_path")
    print("output_json_path:", out_json_path)

    if not out_json_path or not os.path.exists(out_json_path):
        print("Missing output json.")
        return 2

    payload = json.loads(open(out_json_path, "r", encoding="utf-8").read())
    cards = payload.get("elite_idea_cards") if isinstance(payload, dict) else None

    if not isinstance(cards, list) or len(cards) != 2:
        print("Unexpected cards; expected 2")
        print("cards:", cards)
        return 3

    ok = True
    for i, c in enumerate(cards, start=1):
        if not isinstance(c, dict):
            ok = False
            continue
        name = c.get("meta_idea_name")
        img = str(c.get("image_path", "") or "").strip()
        print(f"card{i}.meta_idea_name:", name)
        print(f"card{i}.image_path:", img)
        if not img:
            ok = False
            continue
        abs_img = os.path.join(PROJECT_ROOT, img.replace("/", os.sep))
        if not os.path.exists(abs_img):
            print("  image missing on disk:", abs_img)
            ok = False

    if not ok:
        print("One or more images are missing.\n"
              "Tips:\n"
              "- ensure GEMINI_API_KEY (or ZHIZENGZENG_GEMINI_API_KEY) is set\n"
              "- check network access to api.zhizengzeng.com\n"
              "- check ELITE_IDEAS_DISABLE_T2I is not set to 1")
        return 4

    print("OK: images generated. Open the files under data/elite_ideas/images/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
