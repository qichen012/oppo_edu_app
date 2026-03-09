"""
测试每日简报「更新」功能
依赖：data/daily_briefs/brief_2026-03-09_user1.json 已存在（先跑 test_daily_briefing.py）
"""

import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from skill.daily_briefing_generator import load_daily_briefing, update_daily_briefing

TARGET_DATE = "2026-03-09"
USER_ID = 1

# 模拟用户在手机端输入的补充内容
USER_REFLECT = (
    "今天学完 KNN 之后我一直在想，k 值到底怎么选才合理？感觉太小容易过拟合，"
    "太大又容易欠拟合。另外决策树的信息增益我计算了一遍，发现对连续值特征处理起来很麻烦，"
    "不知道实际工程里是怎么处理的。随机森林的随机性体现在两个地方——样本随机和特征随机，"
    "这一点我觉得很巧妙，后续想深入看看 bagging 和 boosting 的区别。"
)


def test_load_existing_briefing():
    print("=" * 50)
    print("【Step 1】加载原始简报")
    briefing = load_daily_briefing(USER_ID, TARGET_DATE)
    print(f"  ✅ 加载成功：target_date={briefing['target_date']}")
    print(f"  user_reflect 当前值: '{briefing.get('user_reflect', '')}' （空=未填写）")
    print(f"  posterior_insight 前50字: {briefing['posterior_insight'][:50]}...")
    return briefing


def test_update_briefing():
    print("\n" + "=" * 50)
    print("【Step 2】提交用户补充，调用更新接口")
    print(f"  用户输入: {USER_REFLECT[:60]}...")

    result = update_daily_briefing(
        user_id=USER_ID,
        user_reflect=USER_REFLECT,
        target_date=TARGET_DATE,
    )

    print("\n--- 更新后字段概览 ---")
    for key, val in result.items():
        if key in ("posterior_insight", "key_concepts", "user_reflect"):
            preview = str(val)[:80].replace("\n", " ")
            print(f"  {key}: {preview}...")
        else:
            print(f"  {key}: {val}")

    # 验证字段
    print("\n--- 关键字段验证 ---")
    assert result["user_reflect"] == USER_REFLECT, "❌ user_reflect 未正确写入"
    print(f"  ✅ user_reflect 已写入（{len(result['user_reflect'])} 字）")

    assert "updated_at" in result, "❌ 缺少 updated_at 字段"
    print(f"  ✅ updated_at = {result['updated_at']}")

    assert len(result["posterior_insight"]) >= 50, "❌ posterior_insight 太短"
    print(f"  ✅ posterior_insight 字数: {len(result['posterior_insight'])}")

    assert len(result["key_concepts"]) >= 200, "❌ key_concepts 太短"
    print(f"  ✅ key_concepts 字数: {len(result['key_concepts'])}")

    return result


def print_full_result(result):
    print("\n" + "=" * 50)
    print("【更新后完整简报】")
    print(f"\n📌 封面摘要（posterior_insight）：\n{result['posterior_insight']}")
    print(f"\n📖 简报全文（key_concepts）：\n{result['key_concepts']}")


if __name__ == "__main__":
    print(f"🚀 开始测试每日简报更新 | 日期: {TARGET_DATE} | 用户: {USER_ID}\n")

    test_load_existing_briefing()
    result = test_update_briefing()
    print_full_result(result)

    print("\n" + "=" * 50)
    print("✅ 所有测试通过！")
    print(f"⏱️  处理耗时: {result['process_time']}")
    print(f"💾 已覆盖保存至: {os.path.join('data/daily_briefs', f'brief_{TARGET_DATE}_user{USER_ID}.json')}")
