"""\
SparkLink 关联测试：用“课外截图提取”(date_a) 关联 “课内每日简报集合”(date_b)。

需求对齐（按你的描述）：
- 传两个日期：
  - date_a：用于提取那天的截屏（课外信息，来自 data/data_screenshot/analysis/*_full_info.json）
  - date_b：用于提取当天的所有简报（课内知识，来自 data/daily_briefs/brief_{date_b}_user*.json）
- 使用 AI 关联课外知识与课内知识，输出结构化 JSON 并落盘。

使用示例：
1) 推荐：自动扫描本地文件（只给日期即可）
   python test/test_sparklink_association.py --date-a 2026-03-09 --date-b 2026-03-12

2) 联调：启用 mock（不调用 LLM）
   python test/test_sparklink_association.py --date-a 2026-03-09 --date-b 2026-03-12 --mock

可选参数：
- --max-briefs 10    # 限制参与关联的简报数量（按 mtime 从新到旧）
- --analysis-file xxx_full_info.json  # 精确指定 date_a 截图提取文件（文件名或绝对路径）
- --brief-dir data/daily_briefs      # 简报目录
"""

import os
import sys
import json
import time
import glob
import argparse
import re
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from skill.config import ZHIZENGZENG_API_KEY, ZHIZENGZENG_BASE_URL, MODEL_NAME


DATA_ROOT = os.path.join("data", "data_screenshot")
ANALYSIS_DIR_DEFAULT = os.path.join(DATA_ROOT, "analysis")
BRIEFS_DIR_DEFAULT = os.path.join("data", "daily_briefs")


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_date_from_saved_record(record: dict) -> str:
    dt = record.get("screenshot_datetime") or record.get("saved_at")
    if not dt:
        return ""
    return str(dt)[:10]


def _resolve_screenshot_file_for_date(*, analysis_dir: str, target_date: str) -> str:
    if not os.path.isdir(analysis_dir):
        raise FileNotFoundError(
            f"未找到目录: {analysis_dir}，请先通过 /extract_screenshot_info 生成截图提取结果。"
        )

    candidates: list[str] = []
    for fname in os.listdir(analysis_dir):
        if not fname.endswith("_full_info.json"):
            continue
        fpath = os.path.join(analysis_dir, fname)
        try:
            record = _load_json(fpath)
            rec_date = _extract_date_from_saved_record(record)
            if rec_date == target_date:
                candidates.append(fpath)
        except Exception:
            continue

    if not candidates:
        raise FileNotFoundError(
            f"未在 {analysis_dir} 找到日期为 {target_date} 的 *_full_info.json。"
        )

    return max(candidates, key=os.path.getmtime)


def _load_screenshot_info(path: str) -> dict:
    record = _load_json(path)
    return {
        "meta": {
            "source_file": record.get("source_file"),
            "image_path": record.get("image_path"),
            "screenshot_timestamp": record.get("screenshot_timestamp"),
            "screenshot_datetime": record.get("screenshot_datetime"),
            "saved_at": record.get("saved_at"),
        },
        # 兼容 {data: {...}} 与平铺结构两种格式
        "extracted": record.get("data", record),
    }


_USER_ID_RE = re.compile(r"user(\d+)")


def _infer_user_id_from_path(path: str) -> int | None:
    m = _USER_ID_RE.search(os.path.basename(path))
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _scan_briefs_for_date(*, briefs_dir: str, target_date: str) -> list[str]:
    if not os.path.isdir(briefs_dir):
        return []

    patterns = [
        os.path.join(briefs_dir, f"brief_{target_date}_user*.json"),
        os.path.join(briefs_dir, f"brief_{target_date}_user*_*.json"),
    ]

    paths: list[str] = []
    for pat in patterns:
        paths.extend([p for p in glob.glob(pat) if os.path.isfile(p)])

    # 去重 + 新到旧
    seen: set[str] = set()
    deduped = [p for p in paths if not (p in seen or seen.add(p))]
    deduped.sort(key=os.path.getmtime, reverse=True)
    return deduped


def _trim_text(text: Any, *, max_chars: int) -> str:
    if text is None:
        return ""
    s = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 3] + "..."


def _build_prompt_payload(
    *,
    date_a: str,
    date_b: str,
    screenshot: dict,
    briefs: list[tuple[dict, str]],
    per_brief_max_chars: int = 2500,
) -> dict:
    brief_items: list[dict] = []
    for payload, path in briefs:
        brief_items.append(
            {
                "user_id": payload.get("user_id") if isinstance(payload, dict) else None,
                "user_id_inferred": _infer_user_id_from_path(path),
                "target_date": payload.get("target_date") if isinstance(payload, dict) else None,
                "path": path,
                "posterior_insight": _trim_text((payload or {}).get("posterior_insight"), max_chars=600),
                "key_concepts": _trim_text((payload or {}).get("key_concepts"), max_chars=per_brief_max_chars),
                "prompt_questions": (payload or {}).get("prompt_questions"),
            }
        )

    return {
        "date_a": date_a,
        "date_b": date_b,
        "extracurricular": screenshot,
        "curricular_briefs": brief_items,
    }


def _validate_result_schema(result: dict):
    if not isinstance(result, dict):
        raise ValueError("模型输出不是 JSON object")

    for k in ("posterior_insight", "key_concepts", "related_briefs"):
        if k not in result:
            raise ValueError(f"模型输出缺少字段: {k}")

    if not isinstance(result.get("posterior_insight"), str):
        raise ValueError("posterior_insight 必须是 string")
    if not isinstance(result.get("key_concepts"), str):
        raise ValueError("key_concepts 必须是 string")
    if not isinstance(result.get("related_briefs"), list):
        raise ValueError("related_briefs 必须是 list")


def generate_sparklink_association(
    *,
    date_a: str,
    date_b: str,
    analysis_dir: str,
    briefs_dir: str,
    analysis_file: str | None = None,
    max_briefs: int = 10,
    use_mock: bool = False,
) -> tuple[dict, str]:
    start = time.time()

    # 1) 解析截图提取（课外）
    if analysis_file:
        if os.path.isabs(analysis_file):
            screenshot_path = analysis_file
        else:
            screenshot_path = os.path.join(analysis_dir, analysis_file)
        if not os.path.exists(screenshot_path):
            raise FileNotFoundError(f"截图提取文件不存在: {screenshot_path}")
    else:
        screenshot_path = _resolve_screenshot_file_for_date(
            analysis_dir=analysis_dir,
            target_date=date_a,
        )

    screenshot = _load_screenshot_info(screenshot_path)

    # 2) 加载当天所有简报（课内）
    brief_paths = _scan_briefs_for_date(briefs_dir=briefs_dir, target_date=date_b)
    if not brief_paths:
        raise FileNotFoundError(
            f"未在 {briefs_dir} 找到日期为 {date_b} 的简报文件（brief_{date_b}_user*.json）。"
        )

    brief_paths = brief_paths[: max(1, int(max_briefs or 1))]
    briefs: list[tuple[dict, str]] = []
    for p in brief_paths:
        try:
            briefs.append((_load_json(p), p))
        except Exception:
            continue

    if not briefs:
        raise FileNotFoundError(f"找到简报文件但无法读取：{brief_paths[:3]}...")

    payload = _build_prompt_payload(date_a=date_a, date_b=date_b, screenshot=screenshot, briefs=briefs)

    system_prompt = """
你是 SparkLink 课外-课内知识关联引擎。
任务：把 date_a（课外截图提取）中的知识点，与 date_b（课内每日简报集合）中的知识点进行关联。

输入结构：
- extracurricular：来自截图提取的结构化信息（可能含概念/公式/任务线索/疑问点/关键词等）。
- curricular_briefs：date_b 当天的所有简报（可能有多份），每份包含 posterior_insight、key_concepts、prompt_questions。

你必须输出 JSON，且只允许以下字段：
{
  "posterior_insight": "约150字总结：概括课外→课内的主要关联脉络",
  "key_concepts": "不少于500字：详细说明关联链路、概念映射、可复用方法，并给出学习建议",
  "related_briefs": [
    {
      "brief_path": "与该关联最相关的简报 path（从输入里复制）",
      "why_related": "为什么相关（要引用输入证据，不要编造）",
      "linked_concepts": ["概念A", "概念B"],
      "suggested_actions": ["可执行建议1", "可执行建议2"]
    }
  ]
}

约束：
1) 不要虚构输入中没有的信息；不确定就说不确定。
2) 必须显式指出：课外信息中哪些点，对应/补充/反驳/扩展了哪些课内点。
3) related_briefs 按相关性排序（最相关在前），最多 5 条。
4) 仅返回 JSON，不要输出其它文本。
"""

    if use_mock:
        merged = {
            "posterior_insight": f"Mock: 已将 {date_a} 的课外截图信息与 {date_b} 的课内简报集合建立关联。",
            "key_concepts": (
                "Mock: 这是用于联调的关联说明正文。"
                "脚本已完成：截图文件定位与读取、简报集合扫描与截断、payload 组装、输出结构化落盘。"
                "切换到真实模式后，将由模型填充具体的概念映射、证据引用与行动建议。"
            ),
            "related_briefs": [
                {
                    "brief_path": briefs[0][1],
                    "why_related": "Mock: 选取最新的一份简报作为关联示例。",
                    "linked_concepts": ["MockConceptA", "MockConceptB"],
                    "suggested_actions": ["MockAction1", "MockAction2"],
                }
            ],
        }
    else:
        from openai import OpenAI

        client = OpenAI(api_key=ZHIZENGZENG_API_KEY, base_url=ZHIZENGZENG_BASE_URL)
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        merged = json.loads(response.choices[0].message.content)

    _validate_result_schema(merged)

    result = {
        "date_a": date_a,
        "date_b": date_b,
        "posterior_insight": merged.get("posterior_insight", ""),
        "key_concepts": merged.get("key_concepts", ""),
        "related_briefs": merged.get("related_briefs", []),
        "source": {
            "screenshot_path": screenshot_path,
            "brief_paths": [p for _, p in briefs],
            "briefs_dir": briefs_dir,
            "analysis_dir": analysis_dir,
            "max_briefs": max_briefs,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "process_time": f"{time.time() - start:.2f}s",
    }

    os.makedirs(briefs_dir, exist_ok=True)
    safe_a = date_a.replace("-", "")
    safe_b = date_b.replace("-", "")
    save_path = os.path.join(
        briefs_dir,
        f"sparklink_assoc_{safe_a}_to_{safe_b}_{int(time.time())}.json",
    )

    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result, save_path


def main():
    parser = argparse.ArgumentParser(description="SparkLink：课外(date_a) 关联 课内(date_b) 简报集合")
    parser.add_argument("--date-a", type=str, required=True, help="课外截图日期，格式 YYYY-MM-DD")
    parser.add_argument("--date-b", type=str, required=True, help="课内简报日期，格式 YYYY-MM-DD")
    parser.add_argument("--mock", action="store_true", help="启用 mock 模式（不调用 LLM）")
    parser.add_argument(
        "--max-briefs",
        type=int,
        default=int(os.getenv("SPARKLINK_MAX_BRIEFS", "10")),
        help="最多取多少份简报参与关联（按 mtime 新到旧）",
    )
    parser.add_argument(
        "--analysis-dir",
        type=str,
        default=ANALYSIS_DIR_DEFAULT,
        help="截图提取结果目录（默认 data/data_screenshot/analysis）",
    )
    parser.add_argument(
        "--brief-dir",
        type=str,
        default=BRIEFS_DIR_DEFAULT,
        help="每日简报目录（默认 data/daily_briefs）",
    )
    parser.add_argument(
        "--analysis-file",
        type=str,
        default=None,
        help="精确指定截图提取文件（文件名或绝对路径），不传则按 date_a 自动选择最新",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("SparkLink 关联测试开始")
    print(f"date_a(extracurricular)={args.date_a}")
    print(f"date_b(curricular briefs)={args.date_b}")
    print(f"analysis_dir={args.analysis_dir}")
    print(f"brief_dir={args.brief_dir}")
    print(f"max_briefs={args.max_briefs}")
    print(f"analysis_file={args.analysis_file}")
    print(f"mock={args.mock}")

    result, save_path = generate_sparklink_association(
        date_a=args.date_a,
        date_b=args.date_b,
        analysis_dir=args.analysis_dir,
        briefs_dir=args.brief_dir,
        analysis_file=args.analysis_file,
        max_briefs=args.max_briefs,
        use_mock=args.mock,
    )

    print("\n--- 结果预览 ---")
    pi = result.get("posterior_insight", "")
    print(f"posterior_insight: {pi[:120]}...")
    print(f"key_concepts 长度: {len(result.get('key_concepts', '') or '')}")
    print(f"related_briefs 条数: {len(result.get('related_briefs') or [])}")
    print(f"输出文件: {save_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
