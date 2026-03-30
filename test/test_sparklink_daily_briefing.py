"""SparkLink 测试：课外截图（date_a）× 课内简报（date_b）关联融合。

你描述的目标：
- 传两个日期：
    - date_a：用于选取当天截图提取结果（课外信息），来源 data/data_screenshot/analysis/*_full_info.json
    - date_b：用于提取当天“所有简报”（课内知识），来源 data/daily_briefs/brief_{date_b}_user*.json
- 使用 AI 将 date_a 选中的课外知识与 date_b 选中的课内知识进行关联，输出一份融合后的“每日简报格式”结果并落盘。

使用方式示例：
1) 推荐：只传两个日期（user_id 仅用于输出文件命名，可不关心）
     /Users/xwj/Desktop/oppo_edu_app/.venv/bin/python test/test_sparklink_daily_briefing.py \
         --date-a 2026-03-09 \
         --date-b 2026-03-12

2) 联调：启用 mock（不调用 LLM）
     /Users/xwj/Desktop/oppo_edu_app/.venv/bin/python test/test_sparklink_daily_briefing.py \
         --date-a 2026-03-09 \
         --date-b 2026-03-12 \
         --mock
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from skill.sparklink_brief_generator import process_sparklink_brief


def main():
    parser = argparse.ArgumentParser(description="SparkLink 两天融合简报测试")
    parser.add_argument("--date-a", type=str, required=True, help="第一天，格式 YYYY-MM-DD")
    parser.add_argument("--date-b", type=str, required=True, help="第二天，格式 YYYY-MM-DD")
    parser.add_argument("--mock", action="store_true", help="启用 mock 模式（不调用 LLM）")
    parser.add_argument("--user-id", type=int, default=0, help="仅用于输出文件命名（默认0）")
    args = parser.parse_args()

    result = process_sparklink_brief(
        date_a=args.date_a,
        date_b=args.date_b,
        user_id=args.user_id,
        save_to_file=True,
        use_mock=args.mock,
    )

    briefing = result.get("briefing") or {}
    inputs = result.get("inputs") or {}
    stage = result.get("stage")

    print("=" * 60)
    print("SparkLink 测试开始")
    print(f"user_id={args.user_id}, date_a={args.date_a} (课外截图), date_b={args.date_b} (课内简报)")
    if stage:
        print(f"stage={stage}")
    screenshot_paths = inputs.get("screenshot_paths") or []
    brief_paths = inputs.get("brief_paths") or []
    if stage == "cache_hit":
        print("cache_hit: 复用已落盘结果（未重新扫描截图/简报）")
    print(f"screenshots[{len(screenshot_paths)}] (date_a):")
    for p in screenshot_paths[:5]:
        print(f"  - {p}")
    if len(screenshot_paths) > 5:
        print(f"  ... (+{len(screenshot_paths) - 5})")
    print(f"briefs[{len(brief_paths)}] (date_b):")
    for p in brief_paths[:5]:
        print(f"  - {p}")
    if len(brief_paths) > 5:
        print(f"  ... (+{len(brief_paths) - 5})")
    print(f"mock={args.mock}")

    print("\n--- 结果预览 ---")
    pi = str(briefing.get("posterior_insight", ""))
    kc = str(briefing.get("key_concepts", ""))
    print(f"posterior_insight: {pi[:120]}...")
    print(f"key_concepts 长度: {len(kc)}")
    print(f"handout_count: {briefing.get('handout_count')}")
    print(f"输出文件: {result.get('archived_at')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
