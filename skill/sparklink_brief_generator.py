import os
import json
import time
import glob
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from .config import ZHIZENGZENG_API_KEY, ZHIZENGZENG_BASE_URL, MODEL_NAME


DATA_SCREENSHOT_ROOT = os.path.join("data", "data_screenshot")
ANALYSIS_DIR = os.path.join(DATA_SCREENSHOT_ROOT, "analysis")
DAILY_BRIEFS_DIR = os.path.join("data", "daily_briefs")


EXPECTED_BRIEF_KEYS = [
    "user_id",
    "target_date",
    "posterior_insight",
    "key_concepts",
    "created_at",
    "next_review_date",
    "review_stage",
    "user_reflect",
    "source_handouts",
    "handout_count",
    "process_time",
]


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_date_from_saved_record(record: dict) -> str:
    dt = record.get("screenshot_datetime") or record.get("saved_at")
    if not dt:
        return ""
    return str(dt)[:10]


def _resolve_screenshot_files_for_date(*, target_date: str, analysis_dir: str) -> list[str]:
    if not os.path.isdir(analysis_dir):
        raise FileNotFoundError(
            f"未找到目录: {analysis_dir}，请先通过上传截图生成截图提取结果（*_full_info.json）。"
        )

    candidates: list[str] = []
    for fname in os.listdir(analysis_dir):
        if not fname.endswith("_full_info.json"):
            continue
        fpath = os.path.join(analysis_dir, fname)
        if not os.path.isfile(fpath):
            continue
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

    candidates.sort(key=os.path.getmtime, reverse=True)
    return candidates


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
        "extracted": record.get("data", record),
    }


def _load_all_briefs_by_date(*, target_date: str, daily_briefs_dir: str) -> tuple[list[dict], list[str]]:
    pattern = os.path.join(daily_briefs_dir, f"brief_{target_date}_user*.json")
    paths = [p for p in glob.glob(pattern) if os.path.isfile(p)]
    if not paths:
        raise FileNotFoundError(
            f"未在 {daily_briefs_dir} 找到日期为 {target_date} 的简报文件（brief_{target_date}_user*.json）。"
        )

    paths.sort(key=os.path.getmtime, reverse=True)
    briefs: list[dict] = []
    for p in paths:
        try:
            briefs.append(_load_json(p))
        except Exception:
            briefs.append({})
    return briefs, paths


def _brief_minimal_view(brief: dict) -> dict:
    if not isinstance(brief, dict):
        return {"target_date": None, "posterior_insight": "", "key_concepts": "", "source_handouts": []}
    return {
        "target_date": brief.get("target_date"),
        "posterior_insight": brief.get("posterior_insight", ""),
        "key_concepts": brief.get("key_concepts", ""),
        "source_handouts": brief.get("source_handouts", []),
    }


def _build_prompt_payload(
    *,
    date_a: str,
    date_b: str,
    extracurricular_screenshots: list[dict],
    in_class_daily_briefs: list[dict],
) -> dict:
    return {
        "date_a": date_a,
        "date_b": date_b,
        "extracurricular_screenshots": extracurricular_screenshots,
        "in_class_daily_briefs": [_brief_minimal_view(b) for b in in_class_daily_briefs],
    }


def _validate_brief_schema(result: dict):
    actual_keys = list(result.keys())
    if actual_keys != EXPECTED_BRIEF_KEYS:
        raise ValueError(
            "输出字段不匹配每日简报标准。"
            f"\n期望: {EXPECTED_BRIEF_KEYS}"
            f"\n实际: {actual_keys}"
        )


def process_sparklink_brief(
    *,
    date_a: str,
    date_b: str,
    user_id: int = 0,
    force_regen: bool = False,
    save_to_file: bool = True,
    use_mock: bool = False,
    analysis_dir: Optional[str] = None,
    daily_briefs_dir: Optional[str] = None,
) -> dict[str, Any]:
    """生成 SparkLink 融合简报：date_a(课外截图) × date_b(课内简报)。

    - date_a: 从 data/data_screenshot/analysis 选取当天 *_full_info.json（课外信息）
    - date_b: 从 data/daily_briefs 扫描当天所有 brief_{date_b}_user*.json（课内知识）

    返回：
    - success: bool
    - briefing: dict (每日简报 schema)
    - archived_at: str (若 save_to_file)
    - inputs: dict (用于调试)
    """

    analysis_dir = analysis_dir or ANALYSIS_DIR
    daily_briefs_dir = daily_briefs_dir or DAILY_BRIEFS_DIR

    archived_at = os.path.join(
        daily_briefs_dir,
        f"sparklink_brief_{date_a}_{date_b}_user{user_id}.json",
    )

    # Cache: if already generated and caller doesn't force regeneration, reuse on-disk file.
    if not force_regen and os.path.exists(archived_at):
        try:
            cached = _load_json(archived_at)
            if isinstance(cached, dict):
                _validate_brief_schema(cached)
                return {
                    "success": True,
                    "stage": "cache_hit",
                    "briefing": cached,
                    "archived_at": archived_at,
                    "inputs": {
                        "date_a": date_a,
                        "date_b": date_b,
                        "use_mock": use_mock,
                        "force_regen": force_regen,
                    },
                }
        except Exception:
            # Cache is broken/outdated; fall through to regenerate.
            pass

    start = time.time()

    screenshot_paths = _resolve_screenshot_files_for_date(target_date=date_a, analysis_dir=analysis_dir)
    extracurricular = [_load_screenshot_info(p) for p in screenshot_paths]

    in_class_briefs, brief_paths = _load_all_briefs_by_date(target_date=date_b, daily_briefs_dir=daily_briefs_dir)

    prompt_payload = _build_prompt_payload(
        date_a=date_a,
        date_b=date_b,
        extracurricular_screenshots=extracurricular,
        in_class_daily_briefs=in_class_briefs,
    )

    system_prompt = """
你是 SparkLink 学习关联引擎。

任务：
- 输入由两部分组成：
  1) date_a：当天截图提取结果（课外信息，可能多条截图）
  2) date_b：当天所有每日简报（课内知识，可能多份简报）
- 你的目标是：用 date_a 的课外知识去“关联/补充/映射” date_b 的课内知识，产出一份可直接作为学习回顾的融合简报。

你必须重点分析：
1) date_a 截图提取结果里出现的核心概念、公式、术语、题型、任务线索（课外）。
2) date_b 简报里的重点知识点、方法论、练习建议（课内）。
3) 关联点：明确指出“课外信息如何帮助理解/应用/复习课内内容”，至少给出 5 条具体关联点。

输出必须是 JSON，且只允许两个字段：
{
  "posterior_insight": "约150字封面摘要",
  "key_concepts": "不少于500字的融合简报正文"
}

约束：
1) 不要虚构输入中没有的信息。
2) 必须写出清晰的“关联点列表”（编号 1-5+），每条要包含：课外线索 -> 对应课内要点 -> 关联理由。
3) key_concepts 建议结构：
   - 课外信息要点（date_a）
   - 课内简报要点（date_b）
   - 关联点列表（核心）
   - 建议的复习/练习路径
4) 仅返回 JSON，不要输出多余文字。
""".strip()

    if use_mock:
        merged = {
            "posterior_insight": f"Mock: 已完成 {date_a}（课外截图）与 {date_b}（课内简报）的知识关联融合。",
            "key_concepts": (
                "Mock: 这是用于联调的融合简报正文。\n"
                "- 课外信息要点：已从 date_a 扫描到截图提取结果。\n"
                "- 课内简报要点：已从 date_b 扫描到当日全部简报文件。\n"
                "- 关联点列表：\n"
                "  1) 课外概念A -> 课内知识点X -> 理由（Mock）。\n"
                "  2) 课外概念B -> 课内知识点Y -> 理由（Mock）。\n"
                "  3) 课外题型C -> 课内方法Z -> 理由（Mock）。\n"
                "  4) 课外线索D -> 课内复习建议W -> 理由（Mock）。\n"
                "  5) 课外疑点E -> 课内易错点V -> 理由（Mock）。\n"
                "- 后续：关闭 mock 将调用真实模型生成。"
            ),
        }
    else:
        from openai import OpenAI

        if not (ZHIZENGZENG_API_KEY or "").strip():
            raise RuntimeError("Missing ZHIZENGZENG_API_KEY")

        client = OpenAI(api_key=ZHIZENGZENG_API_KEY, base_url=ZHIZENGZENG_BASE_URL)
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        merged = json.loads(response.choices[0].message.content)

    # 与原每日简报保持同结构，避免前端改动
    target_date = date_b
    next_review_date = (
        datetime.strptime(target_date, "%Y-%m-%d") + timedelta(days=1)
    ).strftime("%Y-%m-%d")

    source_handouts: list[str] = []
    for b in in_class_briefs:
        if isinstance(b, dict):
            source_handouts.extend(b.get("source_handouts", []) or [])

    dedup_source_handouts = list(dict.fromkeys([x for x in source_handouts if x]))

    briefing = {
        "user_id": int(user_id),
        "target_date": target_date,
        "posterior_insight": merged.get("posterior_insight", ""),
        "key_concepts": merged.get("key_concepts", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "next_review_date": next_review_date,
        "review_stage": 0,
        "user_reflect": "",
        "source_handouts": dedup_source_handouts,
        "handout_count": len(dedup_source_handouts),
        "process_time": f"{time.time() - start:.2f}s",
    }

    _validate_brief_schema(briefing)

    wrote_path = ""
    if save_to_file:
        os.makedirs(daily_briefs_dir, exist_ok=True)
        with open(archived_at, "w", encoding="utf-8") as f:
            json.dump(briefing, f, ensure_ascii=False, indent=2)
        wrote_path = archived_at

    return {
        "success": True,
        "stage": "generated",
        "briefing": briefing,
        "archived_at": wrote_path,
        "inputs": {
            "date_a": date_a,
            "date_b": date_b,
            "screenshot_paths": screenshot_paths,
            "brief_paths": brief_paths,
            "use_mock": use_mock,
            "force_regen": force_regen,
        },
    }
