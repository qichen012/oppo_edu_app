"""
测试每日简报生成功能
使用今天已有的讲义文件：data/handouts/test02_handout.json (generated_at: 2026-03-09)
"""

import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from skill.daily_briefing_generator import (
    load_today_handouts,
    generate_daily_briefing,
)

TARGET_DATE = "2026-03-09"
USER_ID = 1


def test_load_handouts():
    """测试能否正确读取今天的讲义"""
    print("=" * 50)
    print("【Step 1】加载今天的讲义文件")
    handouts = load_today_handouts(TARGET_DATE)
    assert len(handouts) > 0, f"❌ 未找到 {TARGET_DATE} 的讲义，请检查 data/handouts/ 目录"
    for h in handouts:
        title = h.get("meta", {}).get("title", "未知")
        generated_at = h.get("meta", {}).get("generated_at", "")
        created_at = h.get("created_at", "无时间戳")
        print(f"  ✅ 找到讲义：《{title}》 generated_at={generated_at}  created_at={created_at}")
    print(f"  共加载 {len(handouts)} 份讲义\n")
    return handouts


def test_generate_briefing():
    """测试完整简报生成流程"""
    print("=" * 50)
    print("【Step 2】调用 generate_daily_briefing 生成简报")
    result = generate_daily_briefing(user_id=USER_ID, target_date=TARGET_DATE)

    print("\n--- 返回字段概览 ---")
    for key, val in result.items():
        if key in ("posterior_insight", "key_concepts"):
            preview = str(val)[:80].replace("\n", " ")
            print(f"  {key}: {preview}...")
        else:
            print(f"  {key}: {val}")

    # 验证所有 DB schema 字段都存在
    required_fields = [
        "user_id", "target_date", "posterior_insight", "key_concepts",
        "created_at", "next_review_date", "review_stage", "user_reflect",
        "source_handouts", "handout_count",
    ]
    print("\n--- DB 字段完整性检查 ---")
    for field in required_fields:
        assert field in result, f"❌ 缺少字段：{field}"
        print(f"  ✅ {field}")

    # 验证内容长度
    print("\n--- 内容长度检查 ---")
    insight_len = len(result["posterior_insight"])
    full_len = len(result["key_concepts"])
    print(f"  posterior_insight 字数: {insight_len}（目标约150字）")
    print(f"  key_concepts 字数: {full_len}（目标≥500字）")
    assert insight_len >= 50, f"❌ posterior_insight 太短: {insight_len} 字"
    assert full_len >= 200, f"❌ key_concepts 太短: {full_len} 字"

    # 验证 Ebbinghaus 逻辑
    print("\n--- Ebbinghaus 字段检查 ---")
    assert result["review_stage"] == 0, "❌ review_stage 应为 0"
    assert result["next_review_date"] == "2026-03-10", \
        f"❌ next_review_date 应为 2026-03-10，实际为 {result['next_review_date']}"
    print(f"  ✅ review_stage=0, next_review_date={result['next_review_date']}")

    return result


def print_full_result(result):
    """打印完整简报内容"""
    print("\n" + "=" * 50)
    print("【完整简报内容】")
    print(f"\n📌 封面摘要（posterior_insight）：\n{result['posterior_insight']}")
    print(f"\n📖 简报全文（key_concepts）：\n{result['key_concepts']}")


if __name__ == "__main__":
    print(f"🚀 开始测试每日简报生成 | 目标日期: {TARGET_DATE}\n")

    handouts = test_load_handouts()
    result = test_generate_briefing()
    print_full_result(result)

    print("\n" + "=" * 50)
    print("✅ 所有测试通过！")
    print(f"📊 来源讲义: {result['source_handouts']}")
    print(f"⏱️  处理耗时: {result['process_time']}")
