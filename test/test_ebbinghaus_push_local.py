"""本地冒烟测试：艾宾浩斯“推送/推荐”相关接口。

目标：不启动服务、无需 HTTP 客户端，直接调用路由函数验证返回结构。

覆盖：
1) GET /recommend：应直接返回推荐的简报（三字段）或简报数组。
2) POST /recommend：应返回 recommend_brief_ids 列表。

运行：
    python test/test_ebbinghaus_push_local.py

说明：
- 脚本会在 data/daily_briefs 下为一个测试 user_id 写入几份简报 JSON（不会覆盖你现有真实 user_id 的文件）。
- 如需清理，删除输出中打印的 those brief files 即可。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import date, timedelta


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _make_brief_payload(*, user_id: int, target_date: str, next_review_date: str, overdue_hint: str) -> dict:
    """构造最小可用的 daily_brief JSON。

    注意：load_daily_briefing() 若缺 prompt_questions 会尝试回填（可能触发 LLM）。
    所以这里显式给 prompt_questions，避免额外依赖。
    """

    return {
        "user_id": user_id,
        "target_date": target_date,
        "posterior_insight": f"本地测试简报：{overdue_hint}",
        "key_concepts": f"这是用于本地测试的简报内容：{overdue_hint}",
        "prompt_questions": ["Q1?", "Q2?", "Q3?"],
        "prompt_question": "Q1?\nQ2?\nQ3?",
        "review_stage": 0,
        "next_review_date": next_review_date,
        "source_handouts": "localtest_handout.json",
        "origin": "LOCALTEST",
        "created_at": "2026-03-16T00:00:00Z",
        "updated_at": "2026-03-16T00:00:00Z",
        "process_time": "0.00s",
        "User_reflect": "",
        "user_reflect": "",
    }


def main() -> int:
    # 确保从项目根目录运行（daily_briefing_generator 使用相对路径 data/..）
    root = _project_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    os.chdir(root)

    from run.server import recommend_content_get, recommend_content, RecommendRequest

    # --- 1) 构造几份本地简报文件（用于 GET /recommend 扫描） ---
    user_id = 99999
    today = date.today()

    # 三份简报：两份到期（逾期 5 天、逾期 1 天），一份未到期
    cases = [
        {
            "target_date": (today - timedelta(days=10)).isoformat(),
            "next_review_date": (today - timedelta(days=5)).isoformat(),
            "hint": "overdue=5d (should be selected)",
        },
        {
            "target_date": (today - timedelta(days=3)).isoformat(),
            "next_review_date": (today - timedelta(days=1)).isoformat(),
            "hint": "overdue=1d",
        },
        {
            "target_date": (today - timedelta(days=1)).isoformat(),
            "next_review_date": (today + timedelta(days=2)).isoformat(),
            "hint": "not due yet",
        },
    ]

    daily_briefs_dir = os.path.join(root, "data", "daily_briefs")
    ts = int(time.time())
    created_paths: list[str] = []

    now_ts = int(time.time())

    for i, c in enumerate(cases):
        payload = _make_brief_payload(
            user_id=user_id,
            target_date=c["target_date"],
            next_review_date=c["next_review_date"],
            overdue_hint=c["hint"],
        )
        # 兼容新命名：brief_{target_date}_user{user_id}_{ts}.json
        path = os.path.join(daily_briefs_dir, f"brief_{c['target_date']}_user{user_id}_{ts+i}.json")
        _write_json(path, payload)
        # 关键：GET /recommend 用文件 mtime 近似 last_view_time。
        # 这里通过设置 mtime 来模拟“距离上次查看多久”，让推荐结果稳定可测。
        if "overdue=5d" in c["hint"]:
            mtime = now_ts - 5 * 24 * 3600
        elif "overdue=1d" in c["hint"]:
            mtime = now_ts - 1 * 24 * 3600
        else:
            mtime = now_ts
        try:
            os.utime(path, (mtime, mtime))
        except Exception:
            pass
        created_paths.append(path)

    print("Created local briefs:")
    for p in created_paths:
        print(" -", p)

    # --- 2) 直调 GET /recommend（返回简报本体三字段） ---
    resp = asyncio.run(recommend_content_get(user_id=user_id, limit=1))

    print("\n=== GET /recommend raw response ===")
    try:
        print(json.dumps(resp, ensure_ascii=False, indent=2))
    except Exception:
        print(resp)

    if not isinstance(resp, dict):
        print("FAIL: review_list returned non-dict:", type(resp))
        return 2

    expected_keys = {"posterior_insight", "key_concepts", "prompt_questions"}
    if not isinstance(resp, dict) or set(resp.keys()) != expected_keys:
        print("FAIL: GET /recommend should return 3-field dict, got:", type(resp), getattr(resp, "keys", lambda: [])())
        return 3

    # GET /recommend 只返回简报最小三字段，因此用 posterior_insight 的 hint 验证选中逻辑
    expected_hint = cases[0]["hint"]
    pi = str(resp.get("posterior_insight", "") or "")
    if expected_hint not in pi:
        print("FAIL: selected brief posterior_insight does not contain expected hint")
        print("  expected hint:", expected_hint)
        print("  got posterior_insight:", pi)
        return 4

    print("\nOK: GET /recommend returned a recommended brief")
    print("selected.posterior_insight:", resp.get("posterior_insight"))

    # --- 3) 直调 /recommend（结构校验） ---
    # 这里不追求严格排序（算法依赖 time.time），只验证返回结构与类型。
    req = RecommendRequest(
        user_history=[
            {"brief_id": 0, "last_view_time": 0},
            {"brief_id": 1, "last_view_time": 0},
        ],
        total_briefs=5,
        limit=3,
        source="rss",
        epsilon=0.1,
    )

    rec = asyncio.run(recommend_content(req))

    print("\n=== /recommend raw response ===")
    try:
        print(json.dumps(rec, ensure_ascii=False, indent=2))
    except Exception:
        print(rec)
    if not isinstance(rec, dict) or rec.get("success") is not True:
        print("FAIL: /recommend returned unexpected payload:", rec)
        return 6

    ids = rec.get("recommend_brief_ids")
    if not isinstance(ids, list) or not all(isinstance(x, int) for x in ids):
        print("FAIL: /recommend recommend_brief_ids should be list[int], got:", ids)
        return 7

    print("\nOK: /recommend returned recommend_brief_ids:", ids)

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
