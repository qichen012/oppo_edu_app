"""chat_memory.py

三层文件型对话记忆：
1) 原始对话片段（每次 /chat 一问一答）
2) 每段对话的 250 字左右摘要
3) 每两个摘要再合并为 300 字左右摘要

在下一次对话前，取(2)与(3)各最新两条作为前置知识注入 system prompt。

设计目标：
- 不破坏现有 ChatManager 的历史文件（data/chat_histories/*.json）
- 额外落盘满足你的“三个文件夹”需求
- LLM 不可用时自动降级为规则摘要（保证接口可用）
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ChatMemoryPaths:
    base_dir: str
    segments_dir: str
    segment_summaries_dir: str
    merged_summaries_dir: str


def _project_root_from_this_file() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def get_default_paths(project_root: Optional[str] = None) -> ChatMemoryPaths:
    root = project_root or _project_root_from_this_file()
    base_dir = os.path.join(root, "data", "chat_memory")
    return ChatMemoryPaths(
        base_dir=base_dir,
        segments_dir=os.path.join(base_dir, "segments"),
        segment_summaries_dir=os.path.join(base_dir, "segment_summaries"),
        merged_summaries_dir=os.path.join(base_dir, "merged_summaries"),
    )


def ensure_dirs(paths: ChatMemoryPaths) -> None:
    os.makedirs(paths.segments_dir, exist_ok=True)
    os.makedirs(paths.segment_summaries_dir, exist_ok=True)
    os.makedirs(paths.merged_summaries_dir, exist_ok=True)


def _now_id_prefix() -> str:
    # 可按字符串排序的时间前缀
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _atomic_write_json(file_path: str, payload: Dict[str, Any]) -> None:
    tmp_path = f"{file_path}.tmp.{uuid.uuid4().hex}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, file_path)


def _list_user_files(folder: str, user_id: str, suffix: str = ".json") -> List[str]:
    if not os.path.isdir(folder):
        return []
    files = []
    prefix = f"{user_id}__"
    for name in os.listdir(folder):
        if not name.endswith(suffix):
            continue
        if not name.startswith(prefix):
            continue
        files.append(os.path.join(folder, name))
    files.sort()  # 依赖文件名时间前缀自然排序
    return files


def load_latest_summaries(
    paths: ChatMemoryPaths,
    user_id: str,
    *,
    latest_segment: int = 2,
    latest_merged: int = 2,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """读取最新摘要（每类各取 N 条）。返回 (segment_summaries, merged_summaries)"""

    def _load_last(folder: str, n: int) -> List[Dict[str, Any]]:
        all_files = _list_user_files(folder, user_id)
        selected = all_files[-n:] if n > 0 else []
        out: List[Dict[str, Any]] = []
        for fp in selected:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    out.append(json.load(f))
            except Exception:
                continue
        return out

    return (
        _load_last(paths.segment_summaries_dir, latest_segment),
        _load_last(paths.merged_summaries_dir, latest_merged),
    )


def build_memory_system_prompt(
    segment_summaries: List[Dict[str, Any]],
    merged_summaries: List[Dict[str, Any]],
) -> str:
    """把摘要拼成注入 system 的前置知识。"""
    parts: List[str] = []

    def _fmt(items: List[Dict[str, Any]], title: str) -> None:
        if not items:
            return
        parts.append(f"【{title}】")
        # 这里 items 已按时间升序（因为文件名排序）。为了“最新优先”，倒序展示。
        for it in reversed(items):
            ts = it.get("created_at") or it.get("timestamp") or ""
            summary = (it.get("summary") or "").strip()
            if not summary:
                continue
            if ts:
                parts.append(f"- ({ts}) {summary}")
            else:
                parts.append(f"- {summary}")

    _fmt(segment_summaries, "最近对话摘要（约250字）")
    _fmt(merged_summaries, "最近合并摘要（约300字）")

    if not parts:
        return ""

    parts.append("请在回答用户时，优先参考上述摘要作为长期上下文；若与当前问题冲突，以当前问题为准。")
    return "\n".join(parts)


def _truncate_chars(text: str, max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def _select_summary_provider() -> str:
    forced = (os.getenv("CHAT_SUMMARY_PROVIDER") or "").strip().lower()
    if forced in {"zhizengzeng", "deepseek"}:
        return forced
    forced_chat = (os.getenv("CHAT_PROVIDER") or "").strip().lower()
    if forced_chat in {"zhizengzeng", "deepseek"}:
        return forced_chat
    return "zhizengzeng"


def _llm_summarize(prompt: str, *, max_tokens: int) -> str:
    """调用 LLM 生成摘要（OpenAI SDK 兼容）。不可用时抛异常，由上层降级。"""
    from openai import OpenAI  # 延迟导入，避免环境缺包导致模块 import 失败
    from skill.config import (
        ZHIZENGZENG_BASE_URL,
        ZHIZENGZENG_API_KEY,
        MODEL_NAME,
        DEEPSEEK_BASE_URL,
        DEEPSEEK_API_KEY,
        DEEPSEEK_MODEL,
    )

    if os.getenv("CHAT_MEMORY_DISABLE_LLM") == "1":
        raise RuntimeError("LLM disabled by CHAT_MEMORY_DISABLE_LLM=1")

    provider = _select_summary_provider()
    if provider == "deepseek":
        if not (DEEPSEEK_API_KEY or "").strip():
            raise RuntimeError("Missing DEEPSEEK_API_KEY")
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        model = DEEPSEEK_MODEL
    else:
        if not (ZHIZENGZENG_API_KEY or "").strip():
            raise RuntimeError("Missing ZHIZENGZENG_API_KEY")
        client = OpenAI(api_key=ZHIZENGZENG_API_KEY, base_url=ZHIZENGZENG_BASE_URL)
        model = MODEL_NAME

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是一个擅长中文摘要的助手。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()


def summarize_exchange_250(user_message: str, assistant_message: str) -> str:
    """对一问一答做约 250 字摘要。"""
    prompt = (
        "请把下面这段‘用户-助手’对话总结成一段中文摘要，长度控制在250字左右（不要超过280字），"
        "只输出摘要正文，不要加标题/编号/引号。\n\n"
        f"【用户】{user_message}\n\n"
        f"【助手】{assistant_message}\n"
    )

    try:
        summary = _llm_summarize(prompt, max_tokens=220)
        return _truncate_chars(summary, 280)
    except Exception:
        # 降级：拼接截断
        fallback = f"用户提问：{user_message}。助手回复：{assistant_message}"
        return _truncate_chars(fallback, 260)


def summarize_two_summaries_300(summary_a: str, summary_b: str) -> str:
    """把两段 250 摘要合并成约 300 字摘要。"""
    prompt = (
        "请把下面两段中文摘要进一步合并为一段更高层次的总结，长度控制在300字左右（不要超过340字），"
        "要求：去重、保留关键概念与用户偏好/目标、不要分点，只输出正文。\n\n"
        f"【摘要A】{summary_a}\n\n"
        f"【摘要B】{summary_b}\n"
    )

    try:
        summary = _llm_summarize(prompt, max_tokens=260)
        return _truncate_chars(summary, 340)
    except Exception:
        fallback = f"{summary_a}；{summary_b}"
        return _truncate_chars(fallback, 320)


def record_exchange_and_update_summaries(
    paths: ChatMemoryPaths,
    *,
    user_id: str,
    user_message: str,
    assistant_message: str,
    system_prompt_used: Optional[str],
    segment_summaries_used: List[Dict[str, Any]],
    merged_summaries_used: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """落盘：segment + segment_summary + (可选) merged_summary。

    返回信息用于接口回包/调试：
    {segment_file, segment_summary_file, merged_summary_file?}
    """
    ensure_dirs(paths)

    now_prefix = _now_id_prefix()
    exchange_id = uuid.uuid4().hex

    segment_filename = f"{user_id}__{now_prefix}__segment__{exchange_id}.json"
    segment_path = os.path.join(paths.segments_dir, segment_filename)

    segment_payload: Dict[str, Any] = {
        "id": exchange_id,
        "user_id": user_id,
        "created_at": datetime.now().isoformat(),
        "messages": [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_message},
        ],
        "system_prompt_used": system_prompt_used,
        "memory_used": {
            "segment_summaries": [
                {
                    "id": s.get("id"),
                    "created_at": s.get("created_at"),
                    "file": s.get("file"),
                }
                for s in segment_summaries_used
            ],
            "merged_summaries": [
                {
                    "id": s.get("id"),
                    "created_at": s.get("created_at"),
                    "file": s.get("file"),
                }
                for s in merged_summaries_used
            ],
        },
    }
    _atomic_write_json(segment_path, segment_payload)

    # 250 字摘要
    segment_summary_text = summarize_exchange_250(user_message, assistant_message)
    seg_summary_id = uuid.uuid4().hex
    seg_summary_filename = f"{user_id}__{now_prefix}__seg_summary__{seg_summary_id}.json"
    seg_summary_path = os.path.join(paths.segment_summaries_dir, seg_summary_filename)

    seg_summary_payload: Dict[str, Any] = {
        "id": seg_summary_id,
        "user_id": user_id,
        "created_at": datetime.now().isoformat(),
        "source_segment_id": exchange_id,
        "summary": segment_summary_text,
        "target_chars": 250,
        "file": os.path.basename(seg_summary_path),
    }
    _atomic_write_json(seg_summary_path, seg_summary_payload)

    merged_summary_path: Optional[str] = None

    # 两两合并逻辑：按文件名顺序成对 (1,2), (3,4), ...
    all_seg_files = _list_user_files(paths.segment_summaries_dir, user_id)
    seq = len(all_seg_files)
    if seq >= 2 and seq % 2 == 0:
        file_a, file_b = all_seg_files[-2], all_seg_files[-1]
        try:
            with open(file_a, "r", encoding="utf-8") as f:
                a_obj = json.load(f)
            with open(file_b, "r", encoding="utf-8") as f:
                b_obj = json.load(f)
            a_id = a_obj.get("id")
            b_id = b_obj.get("id")
            merge_key = f"{seq-1:06d}_{seq:06d}__{a_id}__{b_id}"
            merged_filename = f"{user_id}__{now_prefix}__merged__{merge_key}.json"
            merged_path = os.path.join(paths.merged_summaries_dir, merged_filename)

            # 若已存在（理论上不会），跳过
            if not os.path.exists(merged_path):
                merged_text = summarize_two_summaries_300(
                    a_obj.get("summary", ""),
                    b_obj.get("summary", ""),
                )
                merged_payload: Dict[str, Any] = {
                    "id": uuid.uuid4().hex,
                    "user_id": user_id,
                    "created_at": datetime.now().isoformat(),
                    "source_segment_summary_ids": [a_id, b_id],
                    "source_files": [os.path.basename(file_a), os.path.basename(file_b)],
                    "summary": merged_text,
                    "target_chars": 300,
                    "file": os.path.basename(merged_path),
                }
                _atomic_write_json(merged_path, merged_payload)
                merged_summary_path = merged_path
        except Exception:
            # 合并失败不影响主流程
            merged_summary_path = None

    return {
        "segment_file": segment_path,
        "segment_summary_file": seg_summary_path,
        "merged_summary_file": merged_summary_path,
    }
