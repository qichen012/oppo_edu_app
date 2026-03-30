import os
import sys
import time
import json
import uuid
import glob
import shutil
import threading
import base64
import hashlib
import tempfile
from pathlib import Path
from collections import OrderedDict
from datetime import date, timedelta, datetime
from urllib.parse import urlparse
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Form, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import base64
import requests
from skill.pdf_processor import process_pdf_file
from skill.lecture_handout_generator import process_pdf_to_handout
from skill.screenshot_analyzer import (
    analyze_screenshot_bytes,
    extract_all_info_from_screenshot_bytes,
    analyze_screenshot_brief_association,
)
from skill.recommendation_engine import analyze_user_profile, generate_recommendations
from skill.meeting_transcriber import transcribe_audio_file
from skill.query_rewriter import semantic_rewrite
from skill.chat_manager import create_chat_session
from skill.config import UPLOAD_DIR
from skill.chat_memory import (
    get_default_paths,
    load_latest_summaries,
    build_memory_system_prompt,
    record_exchange_and_update_summaries,
)
from skill.ebbinghaus_recommender import recommend_ebbinghaus_brief
from skill.elite_ideas_extractor import process_handout_to_elite_ideas
from skill.daily_briefing_generator import (
    generate_daily_briefing,
    update_daily_briefing,
    load_daily_briefing,
    get_briefs_to_review,
    generate_daily_brief_for_db,
    load_latest_handout_from_storage,
    process_handout_to_daily_brief_for_db,
    save_daily_brief_payload,
    to_minimal_daily_brief_response,
)
from skill.knowledge_tree_generator import process_bytes_to_knowledge_tree
from skill.sparklink_brief_generator import process_sparklink_brief


def _scan_daily_brief_files_for_user(*, user_id: int) -> list[str]:
    """从 data/daily_briefs 扫描指定用户的简报文件路径（兼容多种命名）。"""

    briefs_dir = os.path.join(project_root, "data", "daily_briefs")
    if not os.path.isdir(briefs_dir):
        return []

    patterns = [
        os.path.join(briefs_dir, f"brief_*_user{user_id}.json"),
        os.path.join(briefs_dir, f"brief_*_user{user_id}_*.json"),
        os.path.join(briefs_dir, f"sparklink_brief_*_user{user_id}.json"),
    ]

    paths: list[str] = []
    for pat in patterns:
        paths.extend([p for p in glob.glob(pat) if os.path.isfile(p)])

    # 去重 + 按 mtime 新到旧
    seen: set[str] = set()
    deduped = [p for p in paths if not (p in seen or seen.add(p))]
    deduped.sort(key=os.path.getmtime, reverse=True)
    return deduped


def _build_user_history_from_daily_briefs(*, user_id: int) -> tuple[list[dict], int, list[str]]:
    """基于本地简报文件构造 recommend_ebbinghaus_brief 所需的 user_history。

    说明：当前项目未落盘“用户真实浏览日志”，因此这里采用最小可行的近似：
    - 把每份简报映射为一个 brief_id（按文件 mtime 从新到旧排列）；
    - last_view_time 使用文件 mtime（epoch seconds）。

    这样能让算法按“距离上次查看越久 -> 越需要复习”的方向工作。
    """

    paths = _scan_daily_brief_files_for_user(user_id=user_id)
    total_briefs = len(paths)
    user_history: list[dict] = []

    for brief_id, p in enumerate(paths):
        try:
            last_view_time = int(os.path.getmtime(p))
        except Exception:
            continue
        user_history.append({"brief_id": brief_id, "last_view_time": last_view_time})

    return user_history, total_briefs, paths


# 确保项目根目录在 sys.path 中
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 确保 knowledge_tree 目录在 sys.path 中（该目录内部使用“脚本式导入”，如 from learning_qa import ...）
knowledge_tree_root = os.path.join(project_root, "knowledge_tree")
if os.path.isdir(knowledge_tree_root) and knowledge_tree_root not in sys.path:
    sys.path.insert(0, knowledge_tree_root)


# 初始化 FastAPI
app = FastAPI(title="PDF to NoteCard API")


def _learning_db_api_base_url() -> str:
    return (os.getenv("LEARNING_DB_API_BASE_URL") or "http://localhost:8000/api/v1").rstrip("/")


def _requests_session_for_url(url: str) -> requests.Session:
    """为指定 URL 创建 requests Session。

    在当前环境里可能存在 HTTP_PROXY/HTTPS_PROXY，但未设置 NO_PROXY，
    会导致 Python 对 localhost 的调用走代理并失败。
    """

    s = requests.Session()
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    if host in ("localhost", "127.0.0.1"):
        s.trust_env = False
    return s


class RegisterRequest(BaseModel):
    email: str = Field(..., max_length=100)
    password: str = Field(..., min_length=6)
    name: Optional[str] = Field(None, max_length=45)


class RegisterResponse(BaseModel):
    token: Optional[str] = None
    message: str
    code: int
    user_id: Optional[int] = None


def _try_extract_user_id_from_jwt(token: str | None) -> Optional[int]:
    if not isinstance(token, str) or not token.strip():
        return None
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload_b64 = parts[1]
    # base64url padding
    payload_b64 += "=" * (-len(payload_b64) % 4)
    try:
        payload_raw = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
        payload = json.loads(payload_raw.decode("utf-8"))
    except Exception:
        return None
    v = payload.get("user_id") if isinstance(payload, dict) else None
    return v if isinstance(v, int) else None


def _try_persist_user_screenshot_to_learning_db(
    *,
    user_id: Optional[int],
    image_path: str,
    analysis_payload: Dict[str, Any],
    screenshot_ts: int,
    source_file: Optional[str],
) -> Optional[int]:
    """把截图元数据写入 Learning_DB（MySQL）。失败时返回 None，不影响主流程。"""

    if os.getenv("LEARNING_DB_DISABLE") == "1":
        return None

    base_url = _learning_db_api_base_url()
    url = f"{base_url}/user-screenshots"

    # DB 字段 image_path 最大 100，尽量存相对路径
    try:
        rel_image_path = os.path.relpath(image_path, project_root)
    except Exception:
        rel_image_path = os.path.basename(image_path)

    upload_date = datetime.fromtimestamp(int(screenshot_ts)).date().isoformat()

    vlm_analysis_obj: Dict[str, Any] = {
        "source_file": source_file,
        "screenshot_timestamp": screenshot_ts,
        "image_path": rel_image_path,
        "analysis": analysis_payload,
    }
    vlm_analysis_txt = json.dumps(vlm_analysis_obj, ensure_ascii=False)

    body: Dict[str, Any] = {
        "user_id": user_id,
        "image_path": rel_image_path[:100],
        "vlm_analysis": vlm_analysis_txt,
        "upload_date": upload_date,
    }

    def _post(payload: Dict[str, Any]) -> requests.Response:
        with _requests_session_for_url(url) as session:
            return session.post(url, json=payload, timeout=10)

    try:
        resp = _post(body)
        if 200 <= resp.status_code < 300:
            data = resp.json()
            if isinstance(data, dict) and isinstance(data.get("id"), int):
                return data["id"]
            return None

        # 外键 user_id 不存在时（1452），降级重试：去掉 user_id 以 NULL 写入
        try:
            txt = (resp.text or "").lower()
        except Exception:
            txt = ""

        if os.getenv("LEARNING_DB_VERBOSE") == "1":
            try:
                print("[Learning_DB] persist user_screenshot failed", resp.status_code, (resp.text or "")[:500])
            except Exception:
                pass

        if body.get("user_id") is not None and (
            "foreign key constraint fails" in txt
            or "fk_userscreenshots_userinformation" in txt
            or "cannot add or update a child row" in txt
        ):
            body2 = dict(body)
            body2["user_id"] = None
            resp2 = _post(body2)
            if 200 <= resp2.status_code < 300:
                data2 = resp2.json()
                if isinstance(data2, dict) and isinstance(data2.get("id"), int):
                    return data2["id"]
        return None
    except Exception:
        return None


def _truncate_str(value: Any, max_len: int) -> str:
    if value is None:
        return ""
    try:
        s = str(value)
    except Exception:
        return ""
    s = s.strip()
    if max_len > 0:
        return s[:max_len]
    return s


def _to_int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        s = str(value).strip()
        if not s:
            return None
        return int(s)
    except Exception:
        return None


def _relpath_for_db(path_value: Any, *, max_len: int = 100) -> str:
    """把磁盘路径压缩为适合 DB 字段（尽量相对路径 + 截断）。"""

    if not isinstance(path_value, str):
        return ""

    raw = path_value.strip()
    if not raw:
        return ""

    # DB 里只存路径字符串，不强制存在；尽量用相对路径避免超过 100。
    try:
        if os.path.isabs(raw):
            rel = os.path.relpath(raw, project_root)
        else:
            rel = os.path.relpath(os.path.join(project_root, raw.replace("/", os.sep)), project_root)
        rel = rel.replace(os.sep, "/")
    except Exception:
        rel = os.path.basename(raw)

    return rel[:max_len]


def _learning_db_elite_ideas_enabled() -> bool:
    if os.getenv("LEARNING_DB_DISABLE") == "1":
        return False
    if os.getenv("LEARNING_DB_ELITE_IDEAS_DISABLE") == "1":
        return False
    return True


def _learning_db_elite_ideas_timeout_secs() -> float:
    for k in ("LEARNING_DB_ELITE_IDEAS_TIMEOUT_SECS", "LEARNING_DB_TIMEOUT_SECS"):
        v = str(os.getenv(k, "")).strip()
        if not v:
            continue
        try:
            t = float(v)
            if t > 0:
                return t
        except Exception:
            pass
    return 10.0


_LEARNING_DB_ELITE_IDEAS_PERSIST_LOCK = threading.Lock()


def _learning_db_elite_ideas_persist_index_path() -> str:
    # 与 Elite Ideas 落盘目录同级，避免额外配置
    d = os.path.join(project_root, "data", "elite_ideas")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "learning_db_persist_index.json")


def _load_learning_db_persist_index() -> Dict[str, Any]:
    path = _learning_db_elite_ideas_persist_index_path()
    try:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _atomic_write_json(path: str, obj: Dict[str, Any]) -> None:
    # best-effort atomic write: write temp then replace
    try:
        parent = os.path.dirname(path)
        os.makedirs(parent, exist_ok=True)
    except Exception:
        pass

    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=os.path.dirname(path) or None)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
        tmp_path = None
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def _hash_json_obj(obj: Any) -> str:
    try:
        raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except Exception:
        raw = str(obj).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _normalize_elite_ideas_payload_for_db(*, payload: Dict[str, Any], source_path: str) -> Dict[str, Any]:
    """只保留 DB 相关字段，生成稳定可 hash 的结构（用于幂等 key）。"""

    cards_raw = payload.get("elite_idea_cards")
    cases_raw = payload.get("elite_idea_cases")
    resources_raw = payload.get("external_resources")

    cards: list[dict] = []
    if isinstance(cards_raw, list):
        for i, c in enumerate(cards_raw):
            if not isinstance(c, dict):
                continue
            idx = _to_int_or_none(c.get("card_index"))
            if idx is None:
                idx = i
            cards.append(
                {
                    "card_index": idx,
                    "daily_brief_id": _to_int_or_none(c.get("daily_brief_id")),
                    "origin_concept": _truncate_str(c.get("origin_concept", ""), 100),
                    "meta_idea_name": _truncate_str(c.get("meta_idea_name", ""), 100),
                    "meta_explanation": _truncate_str(c.get("meta_explanation", ""), 100),
                    "create_at": _truncate_str(c.get("create_at", ""), 64),
                }
            )
    cards.sort(key=lambda x: int(x.get("card_index") or 0))

    cases: list[dict] = []
    if isinstance(cases_raw, list):
        for c in cases_raw:
            if not isinstance(c, dict):
                continue
            cases.append(
                {
                    "card_index": _to_int_or_none(c.get("card_index")),
                    "case_title": _truncate_str(c.get("case_title", ""), 100),
                    "case_content": _truncate_str(c.get("case_content", ""), 100),
                    "image_path": _relpath_for_db(c.get("image_path", ""), max_len=100),
                    "query_rewrite": _truncate_str(c.get("query_rewrite", ""), 10000),
                }
            )

    resources: list[dict] = []
    if isinstance(resources_raw, list):
        for r in resources_raw:
            if not isinstance(r, dict):
                continue
            resources.append(
                {
                    "card_index": _to_int_or_none(r.get("card_index")),
                    "title": _truncate_str(r.get("title", ""), 100),
                    "url": _truncate_str(r.get("url", ""), 100),
                    "LLM_context": _truncate_str(r.get("LLM_context", ""), 10000),
                    "source": _truncate_str(r.get("source", ""), 100),
                }
            )

    # 尽量用相对路径做归因，但不强依赖
    try:
        rel_source = os.path.relpath(source_path, project_root).replace(os.sep, "/")
    except Exception:
        rel_source = os.path.basename(source_path)

    return {"source": rel_source, "cards": cards, "cases": cases, "resources": resources}


def _resolve_card_id_for_child(
    *,
    index_hint: Any,
    direct_id_hint: Any,
    idx_to_db_id: Dict[int, int],
    fallback_card_id: Optional[int],
) -> Optional[int]:
    """为 case/resource 解析外键 card_id/meta_id。

    - 优先用 card_index（0/1）映射到新插入的 card.id
    - 其次尝试 meta_id/card_id（若它是 0/1 或 1/2 这种 index）
    - 最后仅在只有 1 张卡时才 fallback
    """

    idx = _to_int_or_none(index_hint)
    if idx is not None:
        if idx in idx_to_db_id:
            return idx_to_db_id[idx]
        if (idx - 1) in idx_to_db_id:
            return idx_to_db_id[idx - 1]

    did = _to_int_or_none(direct_id_hint)
    if did is not None:
        if did in idx_to_db_id:
            return idx_to_db_id[did]
        if (did - 1) in idx_to_db_id:
            return idx_to_db_id[did - 1]

    return fallback_card_id


def _try_persist_elite_ideas_file_to_learning_db(*, elite_ideas_json_path: str) -> None:
    """把落盘的 Elite Ideas（*_elite_ideas_db.json）写入 Learning_DB。

    约束：best-effort（失败不抛出异常、不影响主流程）。
    只写入 DB 存在的列；对超长字段做截断；先写 card 拿到 id，再写 case/resource 回填外键。
    """

    if not _learning_db_elite_ideas_enabled():
        return

    p = str(elite_ideas_json_path or "").strip()
    if not p:
        return

    if not os.path.exists(p) or not os.path.isfile(p):
        return

    try:
        with open(p, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return

    if not isinstance(payload, dict):
        return

    normalized = _normalize_elite_ideas_payload_for_db(payload=payload, source_path=p)
    persist_key = _hash_json_obj(normalized)

    # 幂等：同一份 payload 只入库一次（可续写，避免重复）
    with _LEARNING_DB_ELITE_IDEAS_PERSIST_LOCK:
        index = _load_learning_db_persist_index()
        entry = index.get(persist_key)
        if isinstance(entry, dict) and entry.get("status") == "done":
            return

        if not isinstance(entry, dict):
            entry = {
                "status": "partial",
                "created_at": datetime.utcnow().isoformat() + "Z",
                "source": normalized.get("source"),
                "cards": {},
                "cases_done": [],
                "resources_done": [],
            }
            index[persist_key] = entry
            _atomic_write_json(_learning_db_elite_ideas_persist_index_path(), index)

    cards = payload.get("elite_idea_cards")
    cases = payload.get("elite_idea_cases")
    resources = payload.get("external_resources")

    if not isinstance(cards, list):
        cards = []
    if not isinstance(cases, list):
        cases = []
    if not isinstance(resources, list):
        resources = []

    base_url = _learning_db_api_base_url()
    url_cards = f"{base_url}/elite-idea-cards"
    url_cases = f"{base_url}/elite-idea-cases"
    url_resources = f"{base_url}/external-resources"
    timeout = _learning_db_elite_ideas_timeout_secs()

    def _post(url: str, body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with _requests_session_for_url(url) as session:
            resp = session.post(url, json=body, timeout=timeout)
        if not (200 <= resp.status_code < 300):
            if os.getenv("LEARNING_DB_VERBOSE") == "1":
                try:
                    print("[Learning_DB] persist elite_ideas failed", url, resp.status_code, (resp.text or "")[:500])
                except Exception:
                    pass
            return None
        try:
            data = resp.json()
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    idx_to_db_id: Dict[int, int] = {}
    fallback_card_id: Optional[int] = None

    # 从索引恢复已插入的 cards（用于续写/避免重复）
    try:
        cards_map = entry.get("cards") if isinstance(entry, dict) else None
        if isinstance(cards_map, dict):
            for k, v in cards_map.items():
                ki = _to_int_or_none(k)
                vi = _to_int_or_none(v)
                if ki is not None and vi is not None:
                    idx_to_db_id[ki] = vi
            if len(idx_to_db_id) == 1:
                fallback_card_id = list(idx_to_db_id.values())[0]
    except Exception:
        pass

    # 1) insert cards
    for i, c in enumerate([x for x in cards if isinstance(x, dict)]):
        daily_brief_id = _to_int_or_none(c.get("daily_brief_id"))
        idx = _to_int_or_none(c.get("card_index"))
        if idx is None:
            idx = i

        # 幂等：card 已插入则跳过
        if idx in idx_to_db_id:
            continue

        body = {
            "daily_brief_id": daily_brief_id,
            "origin_concept": _truncate_str(c.get("origin_concept", ""), 100),
            "meta_idea_name": _truncate_str(c.get("meta_idea_name", ""), 100),
            "meta_explanation": _truncate_str(c.get("meta_explanation", ""), 100),
            "create_at": _truncate_str(c.get("create_at", ""), 64) or datetime.utcnow().isoformat(),
        }
        try:
            data = _post(url_cards, body)
        except Exception:
            data = None
        if not isinstance(data, dict):
            continue
        db_id = _to_int_or_none(data.get("id"))
        if db_id is None:
            continue
        idx_to_db_id[idx] = db_id
        if fallback_card_id is None:
            fallback_card_id = db_id

        # 及时落盘索引，避免崩溃后重复插 card
        with _LEARNING_DB_ELITE_IDEAS_PERSIST_LOCK:
            index = _load_learning_db_persist_index()
            e = index.get(persist_key)
            if isinstance(e, dict):
                cards_map = e.get("cards")
                if not isinstance(cards_map, dict):
                    cards_map = {}
                    e["cards"] = cards_map
                cards_map[str(idx)] = db_id
                index[persist_key] = e
                _atomic_write_json(_learning_db_elite_ideas_persist_index_path(), index)

    # 2) insert cases
    cases_done: set[str] = set()
    try:
        raw_done = entry.get("cases_done") if isinstance(entry, dict) else None
        if isinstance(raw_done, list):
            for x in raw_done:
                if isinstance(x, str) and x:
                    cases_done.add(x)
    except Exception:
        pass

    for case in [x for x in cases if isinstance(x, dict)]:
        meta_id = _resolve_card_id_for_child(
            index_hint=case.get("card_index"),
            direct_id_hint=case.get("meta_id"),
            idx_to_db_id=idx_to_db_id,
            fallback_card_id=fallback_card_id if len(idx_to_db_id) == 1 else None,
        )
        if meta_id is None:
            continue

        body = {
            "meta_id": meta_id,
            "case_title": _truncate_str(case.get("case_title", ""), 100),
            "case_content": _truncate_str(case.get("case_content", ""), 100),
            "image_path": _relpath_for_db(case.get("image_path", ""), max_len=100),
            "query_rewrite": _truncate_str(case.get("query_rewrite", ""), 10000),
        }

        case_key = _hash_json_obj({"meta_id": meta_id, **body})
        if case_key in cases_done:
            continue

        try:
            data = _post(url_cases, body)
            if isinstance(data, dict) and _to_int_or_none(data.get("id")) is not None:
                cases_done.add(case_key)
                with _LEARNING_DB_ELITE_IDEAS_PERSIST_LOCK:
                    index = _load_learning_db_persist_index()
                    e = index.get(persist_key)
                    if isinstance(e, dict):
                        e["cases_done"] = sorted(cases_done)
                        index[persist_key] = e
                        _atomic_write_json(_learning_db_elite_ideas_persist_index_path(), index)
        except Exception:
            pass

    # 3) insert external resources
    resources_done: set[str] = set()
    try:
        raw_done = entry.get("resources_done") if isinstance(entry, dict) else None
        if isinstance(raw_done, list):
            for x in raw_done:
                if isinstance(x, str) and x:
                    resources_done.add(x)
    except Exception:
        pass

    for r in [x for x in resources if isinstance(x, dict)]:
        card_id = _resolve_card_id_for_child(
            index_hint=r.get("card_index"),
            direct_id_hint=r.get("card_id"),
            idx_to_db_id=idx_to_db_id,
            fallback_card_id=fallback_card_id if len(idx_to_db_id) == 1 else None,
        )
        if card_id is None:
            continue

        body = {
            "card_id": card_id,
            "title": _truncate_str(r.get("title", ""), 100),
            "url": _truncate_str(r.get("url", ""), 100),
            "LLM_context": _truncate_str(r.get("LLM_context", ""), 10000),
            "source": _truncate_str(r.get("source", ""), 100),
        }

        res_key = _hash_json_obj({"card_id": card_id, **body})
        if res_key in resources_done:
            continue

        try:
            data = _post(url_resources, body)
            if isinstance(data, dict) and _to_int_or_none(data.get("id")) is not None:
                resources_done.add(res_key)
                with _LEARNING_DB_ELITE_IDEAS_PERSIST_LOCK:
                    index = _load_learning_db_persist_index()
                    e = index.get(persist_key)
                    if isinstance(e, dict):
                        e["resources_done"] = sorted(resources_done)
                        index[persist_key] = e
                        _atomic_write_json(_learning_db_elite_ideas_persist_index_path(), index)
        except Exception:
            pass

    # 若 cards 已写入且所有 case/resource 都已标记完成，则标记 done
    try:
        expected_card_indices: set[int] = set()
        for c in normalized.get("cards", []) if isinstance(normalized, dict) else []:
            if isinstance(c, dict):
                ci = _to_int_or_none(c.get("card_index"))
                if ci is not None:
                    expected_card_indices.add(ci)
        cards_complete = expected_card_indices.issubset(set(idx_to_db_id.keys())) and len(expected_card_indices) > 0

        expected_cases = [x for x in (normalized.get("cases") or []) if isinstance(x, dict)] if isinstance(normalized, dict) else []
        expected_resources = [x for x in (normalized.get("resources") or []) if isinstance(x, dict)] if isinstance(normalized, dict) else []
        # 只要 case/resource 数组为空，就认为完成；否则以 done 集合大小为准
        cases_complete = (len(expected_cases) == 0) or (len(cases_done) >= len(expected_cases))
        resources_complete = (len(expected_resources) == 0) or (len(resources_done) >= len(expected_resources))

        if cards_complete and cases_complete and resources_complete:
            with _LEARNING_DB_ELITE_IDEAS_PERSIST_LOCK:
                index = _load_learning_db_persist_index()
                e = index.get(persist_key)
                if isinstance(e, dict):
                    e["status"] = "done"
                    e["done_at"] = datetime.utcnow().isoformat() + "Z"
                    index[persist_key] = e
                    _atomic_write_json(_learning_db_elite_ideas_persist_index_path(), index)
    except Exception:
        pass


@app.post("/register", response_model=RegisterResponse)
async def register_user(request: RegisterRequest):
    """注册用户（写入 Learning_DB）。

    前端只需传 email + password；本服务会转发到 Learning_DB 的 /register 完成入库。
    """

    base_url = _learning_db_api_base_url()
    url = f"{base_url}/register"

    name = request.name
    if not isinstance(name, str) or not name.strip():
        try:
            name = (request.email.split("@", 1)[0] or "").strip() or None
        except Exception:
            name = None

    payload: Dict[str, Any] = {
        "email": request.email,
        "password": request.password,
        "name": name,
    }

    with _requests_session_for_url(url) as session:
        try:
            resp = session.post(url, json=payload, timeout=10)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Learning_DB 注册接口不可用: {e}")

    try:
        data = resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail=f"Learning_DB 返回非 JSON: HTTP {resp.status_code}")

    if not isinstance(data, dict) or "code" not in data or "message" not in data:
        raise HTTPException(status_code=502, detail=f"Learning_DB 返回结构异常: HTTP {resp.status_code}")

    # 兼容：若 Learning_DB 老版本没返回 user_id，则从 token 里解析出来回填
    if isinstance(data, dict) and data.get("user_id") is None:
        uid = _try_extract_user_id_from_jwt(data.get("token"))
        if uid is not None:
            data["user_id"] = uid

    return data


def _kt_create_response(code: int, message: str, data: Any = None, error: str | None = None) -> Dict[str, Any]:
    resp: Dict[str, Any] = {
        "code": code,
        "message": message,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    if data is not None:
        resp["data"] = data
    if error is not None:
        resp["error"] = error
    return resp


# ===== Knowledge Tree (RAG QA) 会话缓存 =====
_KT_SESSION_LOCK = threading.Lock()
_KT_QA_SESSIONS: "OrderedDict[str, Any]" = OrderedDict()


def _kt_get_max_sessions() -> int:
    try:
        v = int(str(os.getenv("KNOWLEDGE_TREE_MAX_SESSIONS", "128")).strip() or "128")
        return max(1, v)
    except Exception:
        return 128


def _kt_get_chroma_path() -> str:
    # 默认与 knowledge_tree/chroma_search.py 一致：./chroma_db（相对当前进程 cwd）
    return str(os.getenv("KNOWLEDGE_TREE_CHROMA_PATH", "./chroma_db")).strip() or "./chroma_db"


def _kt_get_or_create_session(session_id: str):
    session_id = (session_id or "").strip()
    if not session_id:
        raise ValueError("sessionId 不能为空")

    with _KT_SESSION_LOCK:
        existing = _KT_QA_SESSIONS.get(session_id)
        if existing is not None:
            _KT_QA_SESSIONS.move_to_end(session_id)
            return existing

        try:
            from learning_qa import create_qa_system  # type: ignore
        except Exception as e:
            raise RuntimeError(f"导入 knowledge_tree 失败: {e}")

        qa_system = create_qa_system(chroma_path=_kt_get_chroma_path())
        _KT_QA_SESSIONS[session_id] = qa_system
        _KT_QA_SESSIONS.move_to_end(session_id)

        # LRU 淘汰
        max_sessions = _kt_get_max_sessions()
        while len(_KT_QA_SESSIONS) > max_sessions:
            _KT_QA_SESSIONS.popitem(last=False)

        return qa_system


class KnowledgeTreeQARequest(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    query: str
    n_learning_results: int = Field(default=3, ge=1, le=10, alias="nLearningResults")
    n_qa_results: int = Field(default=5, ge=1, le=10, alias="nQaResults")
    save_analysis: bool = Field(default=True, alias="saveAnalysis")
    include_history: bool = Field(default=False, alias="includeHistory")
    debug: bool = Field(default=False, description="是否返回详细错误（仅用于排障）")

    class Config:
        populate_by_name = True


class KnowledgeTreeHistoryRequest(BaseModel):
    session_id: str = Field(..., alias="sessionId")

    class Config:
        populate_by_name = True


class KnowledgeTreeIngestTreeRequest(BaseModel):
    # 二选一：直接传 tree，或传 jobId 从 /v1/pdf/jobs/{job_id}/result 的内存结果取
    tree: Optional[Dict[str, Any]] = None
    job_id: Optional[str] = Field(default=None, alias="jobId")
    collection: str = Field(default="concepts")
    source: str = Field(default="knowledge_tree")
    debug: bool = Field(default=False, description="是否返回详细错误（仅用于排障）")

    class Config:
        populate_by_name = True


def _kt_flatten_tree_to_docs(tree: Dict[str, Any]) -> tuple[list[str], list[dict], list[str]]:
    """把 TreeRoot JSON 扁平化为 (documents, metadatas, ids_suffixes)。"""

    if not isinstance(tree, dict):
        raise ValueError("tree 必须是对象")

    root_id = str(tree.get("id", "root")).strip() or "root"
    root_title = str(tree.get("title", "")).strip()

    documents: list[str] = []
    metadatas: list[dict] = []
    id_suffixes: list[str] = []
    ingested_at = datetime.utcnow().isoformat() + "Z"

    def walk(node: Dict[str, Any], path_titles: list[str], depth: int):
        if not isinstance(node, dict):
            return
        node_id = str(node.get("id", "")).strip()
        title = str(node.get("title", "")).strip()
        content = str(node.get("content", "")).strip()
        related = node.get("relatedNodeId")
        related = None if related in ("", "null", "None") else related

        if node_id and title:
            path_str = " > ".join([t for t in path_titles if t])
            doc = f"标题：{title}\n路径：{path_str}\n内容：{content}".strip()
            documents.append(doc)
            metadatas.append(
                {
                    "rootId": root_id,
                    "rootTitle": root_title,
                    "nodeId": node_id,
                    "title": title,
                    "relatedNodeId": related,
                    "path": path_str,
                    "depth": depth,
                    "ingestedAt": ingested_at,
                }
            )
            id_suffixes.append(node_id)

        children = node.get("children") or []
        if isinstance(children, list):
            for ch in children:
                if isinstance(ch, dict):
                    walk(ch, path_titles + [str(ch.get("title", "")).strip()], depth + 1)

    walk(tree, [root_title], 0)
    return documents, metadatas, id_suffixes


# Elite Ideas 落盘目录（使用绝对路径，避免启动 cwd 不同导致读写不一致）
ELITE_IDEAS_DIR = os.path.join(project_root, "data", "elite_ideas")
ELITE_IDEAS_IMAGE_DIR = os.path.join(ELITE_IDEAS_DIR, "images")
os.makedirs(ELITE_IDEAS_IMAGE_DIR, exist_ok=True)

# 对前端暴露 Elite Ideas 图片静态访问路径：/elite_ideas/images/{filename}
app.mount("/elite_ideas/images", StaticFiles(directory=ELITE_IDEAS_IMAGE_DIR), name="elite_ideas_images")


def _elite_ideas_image_url(image_path: Any) -> str:
    """将落盘 image_path 转为可访问的 URL 路径。

    约束：只允许访问 data/elite_ideas/images 目录下的文件，防止路径穿越。
    返回值为相对 URL（以 / 开头），前端可用当前 origin 拼接。
    """

    if not isinstance(image_path, str):
        return ""

    raw = image_path.strip()
    if not raw:
        return ""

    # 将落盘路径解析为绝对路径（兼容：相对/绝对/不同分隔符）
    if os.path.isabs(raw):
        abs_path = os.path.abspath(raw)
    else:
        abs_path = os.path.abspath(os.path.join(project_root, raw.replace("/", os.sep)))

    base_dir = os.path.abspath(ELITE_IDEAS_IMAGE_DIR)
    try:
        # commonpath 可抵御 ../ 路径穿越
        if os.path.commonpath([base_dir, abs_path]) != base_dir:
            # 兼容：历史缓存可能只存了文件名或其它目录前缀
            filename = os.path.basename(raw)
            if not filename:
                return ""
            abs_path = os.path.abspath(os.path.join(base_dir, filename))
            if os.path.commonpath([base_dir, abs_path]) != base_dir:
                return ""
    except Exception:
        return ""

    if not os.path.isfile(abs_path):
        return ""

    filename = os.path.basename(abs_path)
    return f"/elite_ideas/images/{filename}"


def _guess_image_mime_from_path(path: str) -> str:
    ext = os.path.splitext(path or "")[1].lower().strip(".")
    if ext in {"jpg", "jpeg"}:
        return "image/jpeg"
    if ext == "webp":
        return "image/webp"
    return "image/png"


def _elite_ideas_image_data_url(image_path: Any) -> str:
    """将落盘 image_path 对应的图片内容转为 data URL（base64）。

    - 只允许读取 data/elite_ideas/images 目录下的文件（防路径穿越）
    - 通过环境变量限制最大读取大小（默认 15MB）：ELITE_IDEAS_IMAGE_MAX_BYTES
    """

    if not isinstance(image_path, str):
        return ""

    raw = image_path.strip()
    if not raw:
        return ""

    if os.path.isabs(raw):
        abs_path = os.path.abspath(raw)
    else:
        abs_path = os.path.abspath(os.path.join(project_root, raw.replace("/", os.sep)))

    base_dir = os.path.abspath(ELITE_IDEAS_IMAGE_DIR)
    try:
        if os.path.commonpath([base_dir, abs_path]) != base_dir:
            # 兼容：历史缓存可能只存了文件名或其它目录前缀
            filename = os.path.basename(raw)
            if not filename:
                return ""
            abs_path = os.path.abspath(os.path.join(base_dir, filename))
            if os.path.commonpath([base_dir, abs_path]) != base_dir:
                return ""
    except Exception:
        return ""

    if not os.path.isfile(abs_path):
        return ""

    # 默认 15MB，上限可配置（图片以 data URL 返回，过小会导致前端偶发拿不到图）
    try:
        max_bytes = int(str(os.getenv("ELITE_IDEAS_IMAGE_MAX_BYTES", "15728640")).strip() or "15728640")
    except Exception:
        max_bytes = 15728640

    try:
        size = os.path.getsize(abs_path)
    except Exception:
        return ""

    if max_bytes > 0 and size > max_bytes:
        return ""

    try:
        with open(abs_path, "rb") as f:
            data = f.read()
    except Exception:
        return ""

    if not data:
        return ""

    mime = _guess_image_mime_from_path(abs_path)
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _bg_generate_elite_ideas_from_handout(handout_path: str):
    """后台任务：handout 落盘后自动生成 Elite Ideas。"""
    try:
        result = process_handout_to_elite_ideas(
            handout_filename=handout_path,
            save_to_file=True,
            force_regen=False,
        )
        try:
            out_json_path = result.get("output_json_path") if isinstance(result, dict) else None
            if isinstance(out_json_path, str) and out_json_path.strip():
                _try_persist_elite_ideas_file_to_learning_db(elite_ideas_json_path=out_json_path)
        except Exception:
            # best-effort：落库失败不阻断 Elite Ideas 生成
            pass
        try:
            print(
                "[auto_elite_ideas] stage=", result.get("stage"),
                "handout=", result.get("handout_path"),
                "out_json=", result.get("output_json_path"),
            )
        except Exception:
            pass
    except Exception as e:
        print("[auto_elite_ideas] error=", str(e), "handout=", handout_path)


# ===== 知识树异步 Job 内存存储 =====
# JOBS[job_id] = { status, progress, result, error, created_at }
JOBS: Dict[str, Dict[str, Any]] = {}


class JobCreateResp(BaseModel):
    jobId: str


class JobStatusResp(BaseModel):
    jobId: str
    status: str
    progress: float
    error: Optional[str] = None


def _set_job(job_id: str, **kwargs):
    j = JOBS.get(job_id)
    if j:
        j.update(kwargs)


def _run_knowledge_tree_job(job_id: str, pdf_bytes: bytes, filename: str):
    """后台任务：执行知识树生成 pipeline，结果写入 JOBS"""
    try:
        _set_job(job_id, status="extracting", progress=0.05)
        # 核心处理（内部已包含 outline→enrich 两步 LLM）
        _set_job(job_id, status="llm", progress=0.30)
        result = process_bytes_to_knowledge_tree(pdf_bytes, filename=filename)
        _set_job(job_id, status="done", progress=1.0, result=result["tree"])
    except Exception as e:
        _set_job(job_id, status="error", progress=1.0, error=str(e))


# ===== 数据模型定义 =====
class UserHistory(BaseModel):
    title: str
    clicks: int
    duration: float
    tags: List[str]


class UserProfileRequest(BaseModel):
    user_history: List[UserHistory]


class RecommendRequest(BaseModel):
    user_history: List[Dict[str, Any]]  # 兼容 [{"brief_id": 1, "last_view_time": 1670000000}]
    total_briefs: int = 100  # 简报总数（默认100，可由前端或数据库传入）
    limit: int = 3  # 推荐返回的数量 (Top-K)
    source: str = 'rss'  # 'rss' or 'ddgs'
    epsilon: float = 0.1


class QueryRewriteRequest(BaseModel):
    history: List[Dict[str, str]]  # [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    current_query: str


class ChatRequest(BaseModel):
    user_id: str
    message: str
    system_prompt: str = None  # 可选的系统提示词


class ChatHistoryRequest(BaseModel):
    user_id: str
    limit: int = None  # 限制返回的消息数量


class DailyBriefingRequest(BaseModel):
    user_id: int                  # 用户 ID（对应 DB users.id）
    target_date: str = None       # 目标日期 "YYYY-MM-DD"，默认今天


class UpdateBriefingRequest(BaseModel):
    user_id: int                  # 用户 ID
    user_reflect: str             # 用户在 App 端输入的补充内容/心得
    target_date: str = None       # 目标日期，默认今天


class ScreenshotBriefAssociationRequest(BaseModel):
    user_id: int
    target_date: str = None
    analysis_file: Optional[str] = None  # 可传绝对路径，或 analysis 目录下文件名


class DailyBriefForDbResponse(BaseModel):
    user_id: int
    posterior_insight: str
    key_concepts: str
    created_at: str
    review_stage: int
    User_reflect: str
    source_handouts: str
    origin: str
    prompt_question: str
    prompt_questions: List[str]


class DailyBriefMinimalResponse(BaseModel):
    posterior_insight: str
    key_concepts: str
    prompt_questions: List[str]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SparkLinkBriefRequest(BaseModel):
    date_a: str = Field(..., description="课外截图日期 YYYY-MM-DD（读取 data/data_screenshot/analysis）")
    date_b: str = Field(..., description="课内简报日期 YYYY-MM-DD（扫描 data/daily_briefs/brief_{date_b}_user*.json）")
    user_id: int = Field(0, description="仅用于输出文件命名 sparklink_brief_*_user{user_id}.json")
    mock: bool = Field(False, description="True 则不调用 LLM，用 mock 内容联调")
    save_to_file: bool = Field(True, description="是否落盘到 data/daily_briefs")
    force_regen: bool = Field(False, description="True 则忽略已有 sparklink_brief 缓存，强制重新生成")


class EliteIdeaCardDbResponse(BaseModel):
    id: Optional[int] = None
    daily_brief_id: Optional[int] = None
    origin_concept: str = ""
    meta_idea_name: str
    meta_explanation: str
    create_at: str


@app.post("/process_pdf")
async def process_pdf(file: UploadFile = File(...)):
    """上传 PDF 文件 -> 返回 卡片 JSON（逻辑委托给 skill.ai_handlers）"""
    start_time = time.time()

    file_path = os.path.join(UPLOAD_DIR, file.filename)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件上传失败: {e}")

    try:
        result = process_pdf_file(file_path, filename=file.filename)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate_handout", status_code=204)
async def generate_handout(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
):
    """上传 PDF 文件 -> 生成并落盘讲义（JSON + Markdown），并自动生成对应 Elite Ideas（后台任务）。

    返回：204（不返回内容）。
    """
    start_time = time.time()

    file_path = os.path.join(UPLOAD_DIR, file.filename)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件上传失败: {e}")

    try:
        handout_result = process_pdf_to_handout(file_path, filename=file.filename)

        # 新增 handout 后，自动生成对应 elite ideas（不阻塞主请求）
        archived_at = None
        if isinstance(handout_result, dict):
            archived_at = handout_result.get("archived_at")
        if archived_at and background_tasks is not None:
            background_tasks.add_task(_bg_generate_elite_ideas_from_handout, archived_at)

        return Response(status_code=204)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload_pdf_generate_daily_brief", response_model=DailyBriefMinimalResponse)
async def upload_pdf_generate_daily_brief(
    user_id: int = Form(...),
    source_file: Optional[str] = Form(None),
    handout_filename: Optional[str] = Form(None),
):
    """生成每日简报（按 daily_briefs 表字段对齐，含 prompt_questions）。

    只从 data/handouts 读取已生成讲义来生成简报：
    - 默认取最新的一篇讲义
    - 也可用 source_file 或 handout_filename 精确定位
    """

    # 读存储讲义（默认取最新讲义，也可用 source_file/handout_filename 精确定位）
    try:
        handout = load_latest_handout_from_storage(
            source_file=source_file,
            handout_filename=handout_filename,
        )
        full_payload = process_handout_to_daily_brief_for_db(
            handout=handout,
            user_id=user_id,
            origin="PDF",
            prompt_questions_count=3,
        )

        archived_at = save_daily_brief_payload(payload=full_payload, user_id=user_id)
        full_payload["archived_at"] = archived_at

        return to_minimal_daily_brief_response(payload=full_payload)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/extract_elite_ideas", status_code=204)
async def extract_elite_ideas(
    background_tasks: BackgroundTasks,
    source_file: Optional[str] = Form(None),
    handout_filename: Optional[str] = Form(None),
    daily_brief_id: Optional[int] = Form(None),
    force_regen: bool = Form(False),
):
    """从已落盘讲义提取 Elite Ideas（固定 2 条）并落盘，不返回内容。

    - 不需要上传 PDF。
    - 默认选择 data/handouts 下最新讲义。
    - 若对应的 *_elite_ideas_db.json 已存在，则直接复用（除非 force_regen=true）。
    - 若传入 daily_brief_id，会写入到落盘 JSON 的 elite_idea_cards[*].daily_brief_id。
    """
    try:
        result = process_handout_to_elite_ideas(
            source_file=source_file,
            handout_filename=handout_filename,
            save_to_file=True,
            force_regen=force_regen,
        )
        if not isinstance(result, dict) or not result.get("success"):
            raise HTTPException(status_code=500, detail=str(result.get("error", "Elite Ideas 生成失败")))

        # 最小日志：用于定位“没生成/命中缓存/路径不一致”等问题
        try:
            print(
                "[extract_elite_ideas] stage=", result.get("stage"),
                "handout=", result.get("handout_path"),
                "out_json=", result.get("output_json_path"),
            )
        except Exception:
            pass

        # 防御性校验：确保主产物 JSON 确实已落盘
        out_json_path = result.get("output_json_path")
        if not out_json_path or not os.path.exists(out_json_path):
            raise HTTPException(status_code=500, detail="Elite Ideas 落盘失败：未找到输出 JSON")

        # 可选：把 daily_brief_id 写入落盘 JSON，便于后续直接入库
        if daily_brief_id is not None:
            if out_json_path and os.path.exists(out_json_path):
                try:
                    with open(out_json_path, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                    if isinstance(payload, dict) and isinstance(payload.get("elite_idea_cards"), list):
                        for c in payload["elite_idea_cards"]:
                            if isinstance(c, dict):
                                c["daily_brief_id"] = daily_brief_id
                        with open(out_json_path, "w", encoding="utf-8") as f:
                            json.dump(payload, f, ensure_ascii=False, indent=2)
                except Exception:
                    # 写入失败不阻断主流程
                    pass

        # best-effort：后台落库，不影响接口返回
        if background_tasks is not None:
            try:
                background_tasks.add_task(
                    _try_persist_elite_ideas_file_to_learning_db,
                    elite_ideas_json_path=out_json_path,
                )
            except Exception:
                pass

        return Response(status_code=204)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_elite_ideas")
async def api_get_elite_ideas():
    """返回已落盘的最新一条 Elite Ideas（list 形式，长度为 0 或 1）。

    直接读取 data/elite_ideas 下最新修改的 *_elite_ideas_db.json。
    """

    if not os.path.isdir(ELITE_IDEAS_DIR):
        return []

    candidates = [
        os.path.join(ELITE_IDEAS_DIR, fn)
        for fn in os.listdir(ELITE_IDEAS_DIR)
        if fn.endswith("_elite_ideas_db.json")
    ]
    if not candidates:
        return []

    # 按修改时间倒序：优先返回“图片齐全”的最新一条
    candidates.sort(key=os.path.getmtime, reverse=True)

    def _extract_created_at(payload: dict, *, file_mtime: float | None = None) -> str:
        """提取 Elite Ideas 的创建时间（给前端用）。

        优先读取落盘内容中的 card 字段（历史上叫 create_at）；若没有则回退到文件 mtime。
        """

        try:
            cards = payload.get("elite_idea_cards") if isinstance(payload, dict) else None
        except Exception:
            cards = None

        if isinstance(cards, list) and cards:
            for c in cards:
                if not isinstance(c, dict):
                    continue
                for k in ("created_at", "create_at"):
                    v = c.get(k)
                    if isinstance(v, str) and v.strip():
                        return v.strip()

        if file_mtime is None:
            return ""

        try:
            return datetime.fromtimestamp(float(file_mtime)).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return ""

    def _hydrate_images(p: dict) -> tuple[dict, bool]:
        cards = p.get("elite_idea_cards")
        cases = p.get("elite_idea_cases")

        # 需求：前端主要展示 cases，因此强制 cases 必须带图；cards 不强制。
        # 注意：为了保证“每个 case 对应自己的一张图”，默认不再用 card 的图片回填 case。
        # 若你希望兼容旧缓存（case 无 image_path 时也能展示），可设置：ELITE_IDEAS_CASE_FALLBACK_TO_CARD=1

        card_image_by_index: dict[int, Any] = {}
        if isinstance(cards, list) and cards:
            for card in cards:
                if not isinstance(card, dict):
                    continue
                img_path = card.get("image_path")

                try:
                    idx = int(card.get("card_index"))
                except Exception:
                    idx = None
                if idx is not None and idx not in card_image_by_index:
                    if str(img_path or "").strip():
                        card_image_by_index[idx] = img_path

        # 你的目标结构：2 个 ideas（cards）× 每个 2 个 cases；并且每个 case 必须有图。
        # 这里用 cases[*].card_index 做分组，并只返回 card_index=0/1 的前 2 个 case。

        complete = True

        if isinstance(cards, list):
            norm_cards: list[dict] = [c for c in cards if isinstance(c, dict)]
        else:
            norm_cards = []

        # 固定只展示 2 条 idea
        norm_cards.sort(key=lambda c: int(c.get("card_index")) if str(c.get("card_index", "")).strip().isdigit() else 10**9)
        norm_cards = norm_cards[:2]
        p["elite_idea_cards"] = norm_cards

        card_indices: list[int] = []
        for c in norm_cards:
            try:
                card_indices.append(int(c.get("card_index")))
            except Exception:
                continue

        if len(card_indices) < 2:
            complete = False

        if not isinstance(cases, list) or not cases:
            complete = False
            p["elite_idea_cases"] = []
            return p, complete

        cases_by_card_index: dict[int, list[dict]] = {}
        for case in cases:
            if not isinstance(case, dict):
                continue
            try:
                cidx = int(case.get("card_index"))
            except Exception:
                continue
            cases_by_card_index.setdefault(cidx, []).append(case)

        selected_cases: list[dict] = []
        for cidx in card_indices[:2]:
            group = cases_by_card_index.get(cidx) or []
            group = [c for c in group if isinstance(c, dict)]
            group = group[:2]
            if len(group) < 2:
                complete = False
            selected_cases.extend(group)

        # 最终只返回 4 个 cases（2*2）
        p["elite_idea_cases"] = selected_cases

        for case in selected_cases:
            img_path = case.get("image_path")
            if (
                not str(img_path or "").strip()
                and str(os.getenv("ELITE_IDEAS_CASE_FALLBACK_TO_CARD", "")).strip() == "1"
            ):
                try:
                    cidx = int(case.get("card_index"))
                except Exception:
                    cidx = None
                if cidx is not None and cidx in card_image_by_index:
                    img_path = card_image_by_index[cidx]
                    case["image_path"] = img_path

            case["image_url"] = _elite_ideas_image_url(img_path)
            case["image_data_url"] = _elite_ideas_image_data_url(img_path)
            if not case.get("image_data_url"):
                complete = False

        return p, complete

    for idx, path in enumerate(candidates):
        # 最新文件可能在后台任务中“先落 JSON 后落图片”，这里做一个很短的等待重试
        retries = 3 if idx == 0 else 1
        sleep_s = 0.6
        last_payload: dict | None = None
        last_complete = False

        for attempt in range(retries):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
            except Exception:
                payload = {}

            if not isinstance(payload, dict):
                payload = {}

            hydrated, complete = _hydrate_images(payload)
            last_payload, last_complete = hydrated, complete
            if complete:
                created_at = _extract_created_at(hydrated, file_mtime=os.path.getmtime(path))
                return [
                    {
                        "archived_at": path,
                        "saved_mtime": os.path.getmtime(path),
                        "created_at": created_at,
                        **hydrated,
                    }
                ]

            if attempt < retries - 1:
                time.sleep(sleep_s)

        # 若这个文件不完整，继续尝试下一个更旧的缓存（保证前端拿到带图的完整结果）
        continue

    # 没有任何一份完整结果时：返回最新一份（尽量多带字段），而不是空
    try:
        with open(candidates[0], "r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            payload = {}
        hydrated, _ = _hydrate_images(payload)
        created_at = _extract_created_at(hydrated, file_mtime=os.path.getmtime(candidates[0]))
        return [
            {
                "archived_at": candidates[0],
                "saved_mtime": os.path.getmtime(candidates[0]),
                "created_at": created_at,
                **hydrated,
            }
        ]
    except Exception:
        return []


@app.post("/analyze_screenshot")
async def analyze_screenshot(file: UploadFile = File(...), user_id: Optional[int] = Form(None)):
    """上传截图 -> 与本地笔记库对比，截图保存到 images/，分析结果保存到 analysis/"""
    try:
        image_bytes = await file.read()

        data_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "data_screenshot"))
        images_dir = os.path.join(data_root, "images")
        analysis_dir = os.path.join(data_root, "analysis")
        os.makedirs(images_dir, exist_ok=True)
        os.makedirs(analysis_dir, exist_ok=True)

        ts = int(time.time())
        screenshot_datetime = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        base_name = os.path.splitext(file.filename)[0] if file.filename else "screenshot"
        ext = os.path.splitext(file.filename)[1] if file.filename else ".png"

        # 保存原始截图
        image_save_path = os.path.join(images_dir, f"{ts}_{base_name}{ext}")
        with open(image_save_path, "wb") as f:
            f.write(image_bytes)
        print(f"📸 截图已保存: {image_save_path}")

        # 调用分析
        result = analyze_screenshot_bytes(image_bytes)

        # 保存分析结果 JSON
        analysis_save_path = os.path.join(analysis_dir, f"{ts}_{base_name}_analysis.json")
        with open(analysis_save_path, "w", encoding="utf-8") as f:
            json.dump({
                "source_file": file.filename,
                "user_id": user_id,
                "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "screenshot_timestamp": ts,
                "screenshot_datetime": screenshot_datetime,
                "image_path": image_save_path,
                **result
            }, f, ensure_ascii=False, indent=2)
        print(f"📝 分析结果已保存: {analysis_save_path}")

        # best-effort：写入 Learning_DB.user_screenshots
        screenshot_db_id = _try_persist_user_screenshot_to_learning_db(
            user_id=user_id,
            image_path=image_save_path,
            analysis_payload=result,
            screenshot_ts=ts,
            source_file=file.filename,
        )

        result["image_path"] = image_save_path
        result["analysis_archived_at"] = analysis_save_path
        result["screenshot_timestamp"] = ts
        result["screenshot_datetime"] = screenshot_datetime
        if screenshot_db_id is not None:
            result["user_screenshot_id"] = screenshot_db_id
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/extract_screenshot_info")
async def extract_screenshot_info(file: UploadFile = File(...), user_id: Optional[int] = Form(None)):
    """上传截图 -> 提取截图中的全部可识别信息，结果保存到 analysis/"""
    try:
        image_bytes = await file.read()

        data_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "data_screenshot"))
        images_dir = os.path.join(data_root, "images")
        analysis_dir = os.path.join(data_root, "analysis")
        os.makedirs(images_dir, exist_ok=True)
        os.makedirs(analysis_dir, exist_ok=True)

        ts = int(time.time())
        screenshot_datetime = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        base_name = os.path.splitext(file.filename)[0] if file.filename else "screenshot"
        ext = os.path.splitext(file.filename)[1] if file.filename else ".png"

        # 保存原始截图
        image_save_path = os.path.join(images_dir, f"{ts}_{base_name}{ext}")
        with open(image_save_path, "wb") as f:
            f.write(image_bytes)
        print(f"📸 截图已保存: {image_save_path}")

        # 调用全量信息提取
        result = extract_all_info_from_screenshot_bytes(image_bytes)

        # 保存提取结果 JSON
        analysis_save_path = os.path.join(analysis_dir, f"{ts}_{base_name}_full_info.json")
        with open(analysis_save_path, "w", encoding="utf-8") as f:
            json.dump({
                "source_file": file.filename,
                "user_id": user_id,
                "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "screenshot_timestamp": ts,
                "screenshot_datetime": screenshot_datetime,
                "image_path": image_save_path,
                **result
            }, f, ensure_ascii=False, indent=2)
        print(f"📝 全量信息提取结果已保存: {analysis_save_path}")

        # best-effort：写入 Learning_DB.user_screenshots
        screenshot_db_id = _try_persist_user_screenshot_to_learning_db(
            user_id=user_id,
            image_path=image_save_path,
            analysis_payload=result,
            screenshot_ts=ts,
            source_file=file.filename,
        )

        result["image_path"] = image_save_path
        result["analysis_archived_at"] = analysis_save_path
        result["screenshot_timestamp"] = ts
        result["screenshot_datetime"] = screenshot_datetime
        if screenshot_db_id is not None:
            result["user_screenshot_id"] = screenshot_db_id
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze_screenshot_brief_association")
async def analyze_screenshot_brief_association_api(request: ScreenshotBriefAssociationRequest):
    """读取已保存的截图提取结果，与每日简报做关联分析（不重复图片识别）"""
    try:
        data_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "data_screenshot"))
        analysis_dir = os.path.join(data_root, "analysis")
        os.makedirs(analysis_dir, exist_ok=True)

        # 1) 解析要使用的截图提取文件
        if request.analysis_file:
            if os.path.isabs(request.analysis_file):
                source_analysis_path = request.analysis_file
            else:
                source_analysis_path = os.path.join(analysis_dir, request.analysis_file)
        else:
            candidates = glob.glob(os.path.join(analysis_dir, "*_full_info.json"))
            if not candidates:
                raise HTTPException(status_code=404, detail="未找到截图提取结果，请先调用 /extract_screenshot_info")
            source_analysis_path = max(candidates, key=os.path.getmtime)

        if not os.path.exists(source_analysis_path):
            raise HTTPException(status_code=404, detail=f"截图提取文件不存在: {source_analysis_path}")

        with open(source_analysis_path, "r", encoding="utf-8") as f:
            screenshot_saved = json.load(f)

        extracted_info = screenshot_saved.get("data", screenshot_saved)

        # 2) 读取对应日期的每日简报
        brief = load_daily_briefing(user_id=request.user_id, target_date=request.target_date)

        # 3) 做关联分析
        result = analyze_screenshot_brief_association(extracted_info=extracted_info, daily_brief=brief)

        # 4) 持久化关联结果
        ts = int(time.time())
        assoc_save_path = os.path.join(
            analysis_dir,
            f"{ts}_brief_assoc_user{request.user_id}_{brief.get('target_date', 'unknown')}.json",
        )
        with open(assoc_save_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "source_analysis_file": source_analysis_path,
                    "screenshot_timestamp": screenshot_saved.get("screenshot_timestamp"),
                    "screenshot_datetime": screenshot_saved.get("screenshot_datetime"),
                    "brief_target_date": brief.get("target_date"),
                    **result,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        result["source_analysis_file"] = source_analysis_path
        result["association_archived_at"] = assoc_save_path
        result["screenshot_timestamp"] = screenshot_saved.get("screenshot_timestamp")
        result["screenshot_datetime"] = screenshot_saved.get("screenshot_datetime")
        result["brief_target_date"] = brief.get("target_date")
        return result
    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze_profile")
async def analyze_profile(request: UserProfileRequest):
    """分析用户行为数据，生成用户画像"""
    try:
        user_history = [item.dict() for item in request.user_history]
        result = analyze_user_profile(user_history)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/recommend")
async def recommend_content(request: RecommendRequest):
    """基于用户历史生成推荐内容（艾宾浩斯曲线）"""
    try:
        # 提取用户历史
        user_history = request.user_history
        
        # 调用改进版艾宾浩斯推荐算法
        recommend_ids = recommend_ebbinghaus_brief(
            user_history=user_history, 
            total_briefs=request.total_briefs, 
            top_k=request.limit
        )
        
        return {
            "recommend_brief_ids": recommend_ids,
            "success": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/recommend")
async def recommend_content_get(user_id: int = 3, limit: int = 1):
    """基于本地简报文件生成推荐内容（艾宾浩斯曲线）。

    你希望的测试方式：curl 一下就能跑算法，不用每次手动拼 user_history。
    - user_id 默认 3
    - limit 默认 1

    当前实现用 data/daily_briefs 下的文件 mtime 作为 last_view_time 的近似。

    返回：
    - limit=1 时：直接返回 1 篇简报（posterior_insight/key_concepts/prompt_questions/created_at）。
    - limit>1 时：直接返回简报数组，每个元素同样这 4 个字段。

    说明：此接口不返回 updated_at（更新简报接口会返回）。
    """
    try:
        user_history, total_briefs, paths = _build_user_history_from_daily_briefs(user_id=user_id)
        if total_briefs <= 0:
            empty = to_minimal_daily_brief_response(payload={})
            empty.pop("updated_at", None)
            return empty if (limit or 1) <= 1 else []

        recommend_ids = recommend_ebbinghaus_brief(
            user_history=user_history,
            total_briefs=total_briefs,
            top_k=limit,
        )

        briefs: list[dict] = []
        for brief_id in recommend_ids:
            if not isinstance(brief_id, int) or brief_id < 0 or brief_id >= len(paths):
                continue
            path = paths[brief_id]
            try:
                with open(path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}

            minimal = to_minimal_daily_brief_response(payload=payload)
            minimal.pop("updated_at", None)
            # 兜底：部分旧简报文件可能没有 created_at，这里回退到文件 mtime
            try:
                if not isinstance(minimal.get("created_at"), str) or not minimal.get("created_at").strip():
                    minimal["created_at"] = datetime.utcfromtimestamp(os.path.getmtime(path)).isoformat() + "Z"
            except Exception:
                minimal["created_at"] = minimal.get("created_at") or ""
            # 兼容部分简报 key_concepts 为 dict 的情况：接口统一返回 string，便于前端直接展示
            kc = minimal.get("key_concepts")
            if not isinstance(kc, str):
                minimal["key_concepts"] = json.dumps(kc, ensure_ascii=False, indent=2) if kc is not None else ""
            pi = minimal.get("posterior_insight")
            if not isinstance(pi, str):
                minimal["posterior_insight"] = str(pi) if pi is not None else ""

            briefs.append(minimal)

        if (limit or 1) <= 1:
            return briefs[0] if briefs else to_minimal_daily_brief_response(payload={})
        return briefs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/meeting_transcribe")
async def meeting_transcribe(file: UploadFile = File(...)):
    """接收音频文件，转发到转录服务器，返回会议纪要"""
    # 临时保存上传的音频文件
    temp_audio_path = os.path.join(UPLOAD_DIR, f"temp_audio_{int(time.time())}_{file.filename}")
    
    try:
        # 保存上传的音频文件
        with open(temp_audio_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 调用 skill 模块处理转录
        result = transcribe_audio_file(temp_audio_path)
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 清理临时文件
        if os.path.exists(temp_audio_path):
            try:
                os.remove(temp_audio_path)
            except:
                pass


@app.post("/query_rewrite")
async def query_rewrite(request: QueryRewriteRequest):
    """对用户查询进行语义重写，融合上下文信息"""
    try:
        rewritten_query = semantic_rewrite(request.history, request.current_query)
        return {
            "original_query": request.current_query,
            "rewritten_query": rewritten_query,
            "success": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
async def chat(request: ChatRequest):
    """与 AI 对话，自动维护上下文记忆"""
    try:
        # 1) 读取最近摘要作为“前置知识”（每类最新两条）
        memory_paths = get_default_paths(project_root=project_root)
        seg_summaries, merged_summaries = load_latest_summaries(memory_paths, request.user_id)
        memory_prompt = build_memory_system_prompt(seg_summaries, merged_summaries)

        # 2) 合并外部 system_prompt 与记忆 prompt
        if request.system_prompt and memory_prompt:
            system_prompt = f"{request.system_prompt}\n\n{memory_prompt}"
        elif request.system_prompt:
            system_prompt = request.system_prompt
        else:
            system_prompt = memory_prompt or None

        # 创建或获取用户的对话会话
        chat_manager = create_chat_session(request.user_id)
        
        # 发送消息并获取回复
        response = chat_manager.chat(
            user_message=request.message,
            system_prompt=system_prompt
        )

        # 3) 落盘：原始对话片段 + 250字摘要 + (可选) 两两合并300字摘要
        persist_info = record_exchange_and_update_summaries(
            memory_paths,
            user_id=request.user_id,
            user_message=request.message,
            assistant_message=response,
            system_prompt_used=system_prompt,
            segment_summaries_used=seg_summaries,
            merged_summaries_used=merged_summaries,
        )
        
        return {
            "user_id": request.user_id,
            "user_message": request.message,
            "ai_response": response,
            "memory": {
                "used": {
                    "segment_summaries": len(seg_summaries),
                    "merged_summaries": len(merged_summaries),
                },
                "written": {
                    "segment_file": persist_info.get("segment_file"),
                    "segment_summary_file": persist_info.get("segment_summary_file"),
                    "merged_summary_file": persist_info.get("merged_summary_file"),
                },
            },
            "success": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/history")
async def get_chat_history(request: ChatHistoryRequest):
    """获取用户的对话历史"""
    try:
        chat_manager = create_chat_session(request.user_id)
        history = chat_manager.get_history(limit=request.limit)
        
        return {
            "user_id": request.user_id,
            "history": history,
            "total_messages": len(history),
            "success": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/clear")
async def clear_chat_history(request: ChatHistoryRequest):
    """清空用户的对话历史"""
    try:
        chat_manager = create_chat_session(request.user_id)
        chat_manager.clear_history()
        
        return {
            "user_id": request.user_id,
            "message": "对话历史已清空",
            "success": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate_daily_briefing")
async def api_generate_daily_briefing(request: DailyBriefingRequest):
    """
    基于当天已处理的 PDF 讲义，生成每日简报。

    返回字段与 DB schema 完全对齐，可直接写入 daily_briefs 表：
    - posterior_insight : 约150字封面摘要（封面页展示）
    - key_concepts      : 简报全文（详情页展示）
    - target_date       : 简报所属日期
    - next_review_date  : Ebbinghaus 首次复习日期（明天）
    - review_stage      : 0（刚生成）
    - user_reflect      : 空字符串（用户后续填写）
    - source_handouts   : 当天参与合成的讲义标题列表
    """
    try:
        result = generate_daily_briefing(
            user_id=request.user_id,
            target_date=request.target_date,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_daily_briefing")
async def api_get_daily_briefing(user_id: int, target_date: str = None):
    """获取指定日期的每日简报（直接读本地文件，不重新生成）"""
    try:
        result = load_daily_briefing(user_id=user_id, target_date=target_date)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/update_daily_briefing", response_model=DailyBriefMinimalResponse)
async def api_update_daily_briefing(request: UpdateBriefingRequest):
    """
    融合用户补充内容，更新今日简报。

        流程：读取原简报 → AI 融合用户反思 → 更新 posterior_insight / key_concepts
            → 写入 user_reflect → 覆盖保存文件 → 返回最小三字段（posterior_insight/key_concepts/prompt_questions）

    说明：完整更新后的简报会覆盖写回本地文件（含 User_reflect 等字段）；
    本接口响应体仅返回最小三字段。
    """
    try:
        result = update_daily_briefing(
            user_id=request.user_id,
            user_reflect=request.user_reflect,
            target_date=request.target_date,
        )
        return to_minimal_daily_brief_response(payload=result)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate_sparklink_brief")
async def api_generate_sparklink_brief(request: SparkLinkBriefRequest):
    """SparkLink：用 date_a 的课外截图信息关联 date_b 的课内简报，生成融合简报并可选落盘。"""
    try:
        result = process_sparklink_brief(
            date_a=request.date_a,
            date_b=request.date_b,
            user_id=request.user_id,
            force_regen=bool(request.force_regen),
            save_to_file=bool(request.save_to_file),
            use_mock=bool(request.mock),
        )

        briefing = result.get("briefing") if isinstance(result, dict) else None
        if not isinstance(briefing, dict):
            raise HTTPException(status_code=500, detail="SparkLink 生成失败：返回结构异常")

        # 接口对前端只返回最小两字段（落盘路径/缓存命中等信息仅用于服务端内部）
        return {
            "posterior_insight": briefing.get("posterior_insight", ""),
            "key_concepts": briefing.get("key_concepts", ""),
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


## 已移除：/daily_briefing/review_list
## 为避免与“艾宾浩斯算法推荐接口”混淆，保留 /recommend（GET/POST）作为唯一推荐入口。


# ===== 知识树 Job 接口（与前端约定的三个接口）=====

@app.post("/v1/pdf/jobs", response_model=JobCreateResp)
async def create_pdf_job(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """上传 PDF -> 异步生成知识树，返回 jobId（前端随后轮询状态）"""
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF supported (application/pdf)")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "status": "queued",
        "progress": 0.0,
        "result": None,
        "error": None,
        "created_at": time.time(),
    }

    background_tasks.add_task(_run_knowledge_tree_job, job_id, pdf_bytes, file.filename or "upload.pdf")
    return JobCreateResp(jobId=job_id)


@app.get("/v1/pdf/jobs/{job_id}", response_model=JobStatusResp)
def get_pdf_job(job_id: str):
    """轮询 Job 状态：queued | extracting | llm | done | error"""
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    return JobStatusResp(
        jobId=job_id,
        status=j["status"],
        progress=float(j["progress"]),
        error=j["error"],
    )


@app.get("/v1/pdf/jobs/{job_id}/result")
def get_pdf_job_result(job_id: str):
    """获取已完成 Job 的知识树结果（status=done 时才可取）"""
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    if j["status"] != "done":
        raise HTTPException(status_code=409, detail=f"job not done, status={j['status']}")
    return JSONResponse(content=j["result"])


# ===== Knowledge Tree (RAG QA) 接入到 8001 =====


@app.get("/knowledge_tree/health")
def knowledge_tree_health():
    with _KT_SESSION_LOCK:
        sessions = len(_KT_QA_SESSIONS)
    return _kt_create_response(200, "healthy", {"sessions": sessions})


@app.post("/api/v1/qa/ask")
def knowledge_tree_qa_ask(request: KnowledgeTreeQARequest):
    """兼容 knowledge_tree/api_server.py 的 RAG 问答接口（同端口 8001）。"""

    query = (request.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail=_kt_create_response(400, "query 不能为空", error="INVALID_PARAM"))

    try:
        qa = _kt_get_or_create_session(request.session_id)
        result = qa.answer(
            query=query,
            n_learning_results=int(request.n_learning_results),
            n_qa_results=int(request.n_qa_results),
            save_analysis=bool(request.save_analysis),
        )

        data: Dict[str, Any] = {
            "sessionId": request.session_id,
            "query": result.get("query", query),
            "answer": result.get("answer", ""),
            "learningAnalysis": result.get("learning_analysis"),
            "analysisId": result.get("analysis_id"),
            "learningContext": result.get("learning_context"),
            "qaContext": result.get("qa_context"),
        }

        if bool(request.include_history):
            try:
                data["conversationHistory"] = qa.get_conversation_history()
            except Exception:
                data["conversationHistory"] = []

        return _kt_create_response(200, "success", data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=_kt_create_response(400, str(e), error="INVALID_PARAM"))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=_kt_create_response(500, str(e), error="IMPORT_ERROR"))
    except Exception as e:
        if bool(getattr(request, "debug", False)):
            msg = f"问答失败: {type(e).__name__}: {e}"
            raise HTTPException(status_code=500, detail=_kt_create_response(500, msg, error="MODEL_ERROR"))
        raise HTTPException(status_code=500, detail=_kt_create_response(500, "问答失败", error="MODEL_ERROR"))


@app.post("/knowledge_tree/history")
def knowledge_tree_history(request: KnowledgeTreeHistoryRequest):
    """获取某个 sessionId 的对话历史（仅内存；进程重启会丢失）。"""
    try:
        qa = _kt_get_or_create_session(request.session_id)
        return _kt_create_response(200, "success", {"sessionId": request.session_id, "conversationHistory": qa.get_conversation_history()})
    except Exception as e:
        raise HTTPException(status_code=500, detail=_kt_create_response(500, "获取历史失败", error="SERVER_ERROR"))


@app.post("/knowledge_tree/history/clear")
def knowledge_tree_clear_history(request: KnowledgeTreeHistoryRequest):
    """清空某个 sessionId 的对话历史。"""
    try:
        qa = _kt_get_or_create_session(request.session_id)
        qa.clear_history()
        return _kt_create_response(200, "success", {"sessionId": request.session_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=_kt_create_response(500, "清空历史失败", error="SERVER_ERROR"))


@app.post("/knowledge_tree/ingest/tree")
def knowledge_tree_ingest_tree(request: KnowledgeTreeIngestTreeRequest):
    """把“知识树 JSON”写入 ChromaDB（用于 /api/v1/qa/ask 的检索增强）。

    - 你可以直接传 tree（TreeRoot dict）
    - 或者传 jobId：从 /v1/pdf/jobs 的内存结果里取对应 job 的 result 当作 tree
    """

    collection = (request.collection or "concepts").strip() or "concepts"
    source = (request.source or "knowledge_tree").strip() or "knowledge_tree"

    tree: Optional[Dict[str, Any]] = request.tree
    if tree is None:
        job_id = (request.job_id or "").strip()
        if not job_id:
            raise HTTPException(status_code=400, detail=_kt_create_response(400, "必须提供 tree 或 jobId", error="INVALID_PARAM"))
        j = JOBS.get(job_id)
        if not j or j.get("status") != "done":
            raise HTTPException(status_code=409, detail=_kt_create_response(409, "job 未完成或不存在", error="JOB_NOT_READY"))
        tree = j.get("result")

    debug = bool(getattr(request, "debug", False))

    try:
        documents, metadatas, id_suffixes = _kt_flatten_tree_to_docs(tree)
        if not documents:
            raise HTTPException(status_code=400, detail=_kt_create_response(400, "tree 中未提取到可入库节点", error="INVALID_TREE"))

        # 注入 source 元数据
        def _sanitize_metadata(meta: dict) -> dict:
            cleaned: dict = {}
            for k, v in (meta or {}).items():
                if v is None:
                    continue
                if isinstance(v, (str, int, float, bool)):
                    cleaned[str(k)] = v
                else:
                    # chromadb metadata 仅允许标量；其余类型转字符串
                    cleaned[str(k)] = str(v)
            return cleaned

        metadatas = [
            _sanitize_metadata({**m, "source": source}) if isinstance(m, dict) else {"source": source}
            for m in metadatas
        ]

        batch_id = str(uuid.uuid4())
        ids = [f"{batch_id}:{suf}" for suf in id_suffixes]

        try:
            from chroma_search import ContextualCompressionSearch  # type: ignore
        except Exception as e:
            raise HTTPException(status_code=500, detail=_kt_create_response(500, f"导入 chroma_search 失败: {e}", error="IMPORT_ERROR"))

        search = ContextualCompressionSearch(collection_name=collection, chroma_path=_kt_get_chroma_path())

        try:
            search.add_documents(documents=documents, metadatas=metadatas, ids=ids)
        except Exception as e:
            if debug:
                msg = f"入库失败: {type(e).__name__}: {e}"
                raise HTTPException(
                    status_code=500,
                    detail=_kt_create_response(
                        500,
                        msg,
                        data={"collection": collection, "chromaPath": _kt_get_chroma_path(), "docCount": len(documents)},
                        error="DATABASE_ERROR",
                    ),
                )
            raise HTTPException(status_code=500, detail=_kt_create_response(500, "入库失败", error="DATABASE_ERROR"))

        try:
            count = int(search.get_document_count())
        except Exception:
            count = None

        return _kt_create_response(
            200,
            "success",
            {
                "batchId": batch_id,
                "collection": collection,
                "ingested": len(ids),
                "count": count,
            },
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=_kt_create_response(400, str(e), error="INVALID_PARAM"))
    except Exception as e:
        if debug:
            msg = f"入库失败: {type(e).__name__}: {e}"
            raise HTTPException(status_code=500, detail=_kt_create_response(500, msg, error="DATABASE_ERROR"))
        raise HTTPException(status_code=500, detail=_kt_create_response(500, "入库失败", error="DATABASE_ERROR"))


# 启动命令提示
if __name__ == "__main__":
    print("启动服务中... 请在浏览器访问 http://127.0.0.1:8001/docs 查看接口文档")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)