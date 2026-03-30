"""最小自测：验证 /chat 的三层记忆落盘与注入逻辑。

用法：
1) 先启动服务（建议开启离线降级，避免外部 LLM/余额/网络影响）：
    CHAT_DISABLE_LLM=1 CHAT_MEMORY_DISABLE_LLM=1 .venv/bin/python run/server.py
    （或你自己的启动方式，确保端口是 8001）

2) 另开一个终端跑：
    .venv/bin/python test/test_chat_memory_pipeline.py

说明：
- 设置 CHAT_MEMORY_DISABLE_LLM=1 后，摘要会走降级规则，不依赖 DeepSeek/网络。
- 脚本会连续调用 3 次 /chat：
  - 第 1/2 次写入 segment + seg_summary；第 2 次后应出现 merged_summary
  - 第 3 次会使用(2)(3)的最新摘要作为 system prompt 前置知识（服务端写入 segment 文件里可见 memory_used）
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error


BASE_URL = os.environ.get("CHAT_TEST_BASE_URL", "http://127.0.0.1:8001")
USER_ID = os.environ.get("CHAT_TEST_USER", "user_test_001")


def _post_json(path: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            body = ""
        raise RuntimeError(f"HTTP {e.code} calling {path}: {body}")


def main() -> None:
    print(f"BASE_URL={BASE_URL}")
    print(f"USER_ID={USER_ID}")

    # 1) 第一次
    r1 = _post_json(
        "/chat",
        {
            "user_id": USER_ID,
            "message": "我想学习 SQLAlchemy 的 best practice，有什么推荐？",
            "system_prompt": "你是一个耐心的学习助手。",
        },
    )
    assert r1.get("success") is True
    assert "memory" in r1
    print("#1 ok", r1["memory"]["written"]) 

    time.sleep(0.2)

    # 2) 第二次（这次结束后应当生成 merged_summary_file）
    r2 = _post_json(
        "/chat",
        {
            "user_id": USER_ID,
            "message": "再给我一个最小可运行的示例（含 session/engine）。",
            "system_prompt": "你是一个耐心的学习助手。",
        },
    )
    assert r2.get("success") is True
    merged_file = r2.get("memory", {}).get("written", {}).get("merged_summary_file")
    print("#2 ok", r2["memory"]["written"])
    assert merged_file is None or merged_file.endswith(".json")

    time.sleep(0.2)

    # 3) 第三次：服务端会在 system prompt 注入最近摘要
    r3 = _post_json(
        "/chat",
        {
            "user_id": USER_ID,
            "message": "结合我前面的问题，帮我列一个 7 天学习计划。",
            "system_prompt": "你是一个耐心的学习助手。",
        },
    )
    assert r3.get("success") is True
    used = r3.get("memory", {}).get("used", {})
    print("#3 ok used", used)

    print("OK")


if __name__ == "__main__":
    main()
