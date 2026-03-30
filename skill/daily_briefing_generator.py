import os
import json
import time
import glob
from typing import Any
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from openai import OpenAI
from .config import ZHIZENGZENG_API_KEY, ZHIZENGZENG_BASE_URL, MODEL_NAME, OUTPUT_DIR

import requests

# 初始化客户端
client = OpenAI(api_key=ZHIZENGZENG_API_KEY, base_url=ZHIZENGZENG_BASE_URL)

# 讲义存储目录（与 lecture_handout_generator 保持一致）
HANDOUT_DIR = os.path.join(os.path.dirname(OUTPUT_DIR), "handouts")

# 每日简报存储目录
DAILY_BRIEFS_DIR = os.path.join(os.path.dirname(OUTPUT_DIR), "daily_briefs")
os.makedirs(DAILY_BRIEFS_DIR, exist_ok=True)

# Ebbinghaus 各阶段距下次复习的天数间隔
EBBINGHAUS_INTERVALS = [1, 2, 4, 7, 15, 30, 60, 120]  # stage 0->1 间隔1天, 依此类推


def _normalize_source_handouts(source_handouts: object) -> str:
    """将 source_handouts 归一化为可读字符串（兼容 list/str）。"""

    if isinstance(source_handouts, str):
        return source_handouts.strip()
    if isinstance(source_handouts, list):
        items: list[str] = []
        for x in source_handouts:
            if isinstance(x, str) and x.strip():
                items.append(x.strip())
        return "、".join(items)
    return ""


def _find_daily_brief_path(*, user_id: int, target_date: str) -> str:
    """定位某天的简报文件路径。

    兼容两种落盘命名：
    - 旧：brief_{target_date}_user{user_id}.json
    - 新：brief_{target_date}_user{user_id}_{ts}.json
    优先旧文件；否则取新文件中修改时间最新的一份。
    """

    candidates: list[str] = []

    # 旧命名（历史接口）
    legacy_path = os.path.join(DAILY_BRIEFS_DIR, f"brief_{target_date}_user{user_id}.json")
    if os.path.isfile(legacy_path):
        candidates.append(legacy_path)

    # 新命名（保存完整 payload 的归档文件）
    pattern = os.path.join(DAILY_BRIEFS_DIR, f"brief_{target_date}_user{user_id}_*.json")
    candidates.extend([p for p in glob.glob(pattern) if os.path.isfile(p)])

    if not candidates:
        raise FileNotFoundError(f"未找到简报文件: {legacy_path} 或 {pattern}，请先生成今日简报")

    # 选择“最新被写入”的那一份：更符合“更新最新简报”的直觉
    return max(candidates, key=os.path.getmtime)


def load_today_handouts(target_date: str = None) -> list[dict]:
    """
    扫描 handouts 目录，加载目标日期（默认今天）生成的所有讲义。
    匹配规则：JSON 文件内 meta.generated_at == target_date
    """
    if target_date is None:
        target_date = datetime.now().strftime("%Y-%m-%d")

    handouts = []
    if not os.path.isdir(HANDOUT_DIR):
        return handouts

    for fname in os.listdir(HANDOUT_DIR):
        if not fname.endswith("_handout.json"):
            continue
        fpath = os.path.join(HANDOUT_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 优先用 meta.generated_at 匹配，兜底用文件修改时间
            generated_at = data.get("meta", {}).get("generated_at", "")
            if generated_at == target_date:
                handouts.append(data)
                continue
            # 兜底：检查文件修改日期
            mtime = os.path.getmtime(fpath)
            if datetime.fromtimestamp(mtime).strftime("%Y-%m-%d") == target_date:
                handouts.append(data)
        except Exception as e:
            print(f"⚠️ 读取讲义失败 {fname}: {e}")

    return handouts


def _compress_handout(handout: dict) -> str:
    """将单份讲义压缩为简洁的文本摘要，供 LLM 合成简报使用"""
    meta = handout.get("meta", {})
    title = meta.get("title", "未知标题")
    overview = handout.get("overview", "")
    summary = handout.get("summary", "")

    section_titles = [s.get("title", "") for s in handout.get("sections", [])]
    key_terms = []
    for s in handout.get("sections", []):
        for kc in s.get("key_concepts", []):
            term = kc.get("term", "")
            if term:
                key_terms.append(term)

    lines = [
        f"【{title}】",
        f"概述：{overview}",
        f"章节：{'、'.join(section_titles)}",
        f"核心概念：{'、'.join(key_terms[:10])}",
        f"总结：{summary}",
    ]
    return "\n".join(lines)


def generate_briefing_from_handouts(handouts: list[dict], target_date: str) -> dict:
    """
    调用 LLM，将当天多份讲义合成每日简报。

    返回字段与 DB schema 对齐：
    {
        "posterior_insight": "约150字的封面摘要",
        "key_concepts":      "简报全文（详情页展示）",
    }
    """
    if not handouts:
        raise ValueError("当天没有可用的讲义数据")

    compressed = "\n\n---\n\n".join(
        [_compress_handout(h) for h in handouts]
    )
    titles = [h.get("meta", {}).get("title", "未知") for h in handouts]

    system_prompt = f"""
你是一位资深知识整合师。今天是 {target_date}，用户今天一共学习了 {len(handouts)} 份材料，
分别是：{' / '.join(titles)}。

请基于下方所有材料的摘要，生成一篇**每日学习简报**。

输出必须是纯 JSON，结构如下，不要包含任何 Markdown 代码块：

{{
    "posterior_insight": "封面摘要：约150字，使用专业、简洁的第三人称陈述语气，概括今天学习材料的核心主题、涵盖的知识体系范围以及最重要的知识点或方法论，适合作为简报封面的内容摘要，供读者快速掌握今日学习要点",
    "key_concepts": "简报全文：完整的每日简报正文，包含以下部分：\\n1. 今日学习总览（介绍几份材料的主题）\\n2. 各材料核心知识点梳理（每份材料单独一段，提炼3-5个核心概念并简要解释）\\n3. 跨材料联系与洞见（发现各材料之间的共性规律或互补关系）\\n4. 今日学习建议（1-2条，针对今天的内容给出学习侧重和复习提示）\\n全文不少于500字，使用清晰的段落结构"
}}
"""

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"以下是今天所有讲义的摘要：\n\n{compressed}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
        )
        raw = response.choices[0].message.content
        return json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"LLM 调用失败: {e}")


def generate_daily_briefing(user_id: int, target_date: str = None) -> dict:
    """
    每日简报生成主函数。

    Args:
        user_id:     用户 ID（对应 DB 中的 user_id 外键）
        target_date: 目标日期字符串 "YYYY-MM-DD"，默认今天

    Returns:
        与 DB schema 字段完全对齐的 dict，可直接插入数据库：
        {
            "user_id":          int,
            "target_date":      "YYYY-MM-DD",
            "posterior_insight": "~150字封面摘要",
            "key_concepts":     "简报全文",
            "created_at":       "2026-03-09T08:00:00+00:00",
            "next_review_date": "YYYY-MM-DD",   # 第一次复习：明天
            "review_stage":     0,               # 刚生成
            "user_reflect":     "",              # 用户尚未填写
            "source_handouts":  ["title1", ...], # 来源讲义标题列表
            "handout_count":    int
        }
    """
    if target_date is None:
        target_date = datetime.now().strftime("%Y-%m-%d")

    start_time = time.time()

    # 1. 加载当天讲义
    handouts = load_today_handouts(target_date)
    if not handouts:
        raise ValueError(f"{target_date} 没有找到任何讲义文件，请先处理 PDF")

    # 2. LLM 合成简报
    briefing_content = generate_briefing_from_handouts(handouts, target_date)

    # 3. 计算 Ebbinghaus 首次复习日期（stage=0 → interval=1天）
    target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    next_review_date = (target_dt + timedelta(days=EBBINGHAUS_INTERVALS[0])).strftime("%Y-%m-%d")

    # 4. 组装返回结果
    source_titles = [h.get("meta", {}).get("title", "未知") for h in handouts]
    created_at = datetime.now(timezone.utc).isoformat()

    result = {"user_id": user_id,
              "target_date": target_date,
              "posterior_insight": briefing_content.get("posterior_insight", ""),
              "key_concepts": briefing_content.get("key_concepts", ""),
              "created_at": created_at,
              "next_review_date": next_review_date,
              "review_stage": 0,
              "user_reflect": "",
              "User_reflect": "",
              "source_handouts": source_titles,
              "origin": "PDF",
              "handout_count": len(handouts),
              "process_time": f"{time.time() - start_time:.2f}s",
              }

    # 4.1 生成引导性思考题（用于前端展示/落库对齐）
    prompt_questions = generate_prompt_questions(
        posterior_insight=result.get("posterior_insight", ""),
        key_concepts=result.get("key_concepts", ""),
        count=3,
    )
    result["prompt_questions"] = prompt_questions
    result["prompt_question"] = "\n".join(prompt_questions)

    # 4.2 落盘前：同时写入 Learning_DB（MySQL），成功则回填 daily_brief_id
    daily_brief_id = _try_persist_daily_brief_to_learning_db_api(result)
    if daily_brief_id is not None:
        result["daily_brief_id"] = daily_brief_id

    # 5. 保存到本地 data/daily_briefs/
    save_path = os.path.join(
        DAILY_BRIEFS_DIR,
        f"brief_{target_date}_user{user_id}.json"
    )
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"💾 每日简报已保存: {save_path}")
    result["archived_at"] = save_path

    return result


def _learning_db_api_base_url() -> str:
    # docker compose 暴露到宿主机 8000（默认值）；如部署不同环境可用 env 覆盖
    return (os.getenv("LEARNING_DB_API_BASE_URL") or "http://localhost:8000/api/v1").rstrip("/")


def _build_daily_brief_create_payload(payload: dict) -> dict[str, Any]:
    """将本项目的简报 payload 映射为 Learning_DB API 的 DailyBriefCreate 结构。"""

    user_id = payload.get("user_id")

    posterior_insight = payload.get("posterior_insight")
    if not isinstance(posterior_insight, str):
        posterior_insight = str(posterior_insight) if posterior_insight is not None else ""
    posterior_insight = _truncate_chars(posterior_insight, 100)

    key_concepts = payload.get("key_concepts")
    if not isinstance(key_concepts, str):
        key_concepts = str(key_concepts) if key_concepts is not None else ""

    created_at = payload.get("created_at")
    if isinstance(created_at, str) and created_at.strip():
        created_at_value: Any = created_at
    elif isinstance(created_at, datetime):
        created_at_value = created_at.isoformat()
    else:
        created_at_value = datetime.now(timezone.utc).isoformat()

    review_stage = payload.get("review_stage")
    if not isinstance(review_stage, int):
        try:
            review_stage = int(review_stage)
        except Exception:
            review_stage = 0

    user_reflect = payload.get("User_reflect")
    if not isinstance(user_reflect, str):
        user_reflect = payload.get("user_reflect")
    if not isinstance(user_reflect, str):
        user_reflect = ""

    source_handouts_raw = payload.get("source_handouts")
    source_handouts = _truncate_chars(_normalize_source_handouts(source_handouts_raw), 100)

    origin = payload.get("origin")
    if origin not in ("SC", "PDF"):
        origin = "PDF"

    prompt_question = payload.get("prompt_question")
    if not isinstance(prompt_question, str) or not prompt_question.strip():
        qs = payload.get("prompt_questions")
        if isinstance(qs, list):
            prompt_question = "\n".join([q.strip() for q in qs if isinstance(q, str) and q.strip()])
        else:
            prompt_question = ""

    return {
        "user_id": user_id,
        "posterior_insight": posterior_insight,
        "key_concepts": key_concepts,
        "created_at": created_at_value,
        "review_stage": review_stage,
        "User_reflect": user_reflect,
        "source_handouts": source_handouts,
        "origin": origin,
        "prompt_question": prompt_question,
    }


def _try_persist_daily_brief_to_learning_db_api(payload: dict) -> int | None:
    """把简报写入 Learning_DB（MySQL）。失败时返回 None，不影响主流程。"""

    if os.getenv("LEARNING_DB_DISABLE") == "1":
        return None

    try:
        base_url = _learning_db_api_base_url()
        url = f"{base_url}/daily-briefs"

        body = _build_daily_brief_create_payload(payload)

        parsed = urlparse(base_url)
        host = (parsed.hostname or "").lower()
        disable_env_proxy = host in ("localhost", "127.0.0.1")

        with requests.Session() as session:
            if disable_env_proxy:
                session.trust_env = False

            def _post(b: dict) -> requests.Response:
                return session.post(url, json=b, timeout=10)

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
                print("[Learning_DB] persist failed", resp.status_code, resp.text[:500])
            except Exception:
                pass

        if body.get("user_id") is not None and (
            "foreign key constraint fails" in txt
            or "fk_dailybriefs_userinformation" in txt
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

        return None
    except Exception:
        return None


def _truncate_chars(text: str, max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def generate_prompt_questions(posterior_insight: str, key_concepts: str, count: int = 3) -> list[str]:
    """基于简报内容生成引导性思考题（用于前端在正文后展示）。

    返回：字符串列表（建议 3 条）。
    若 LLM 不可用则返回兜底问题。
    """

    if count <= 0:
        return []

    # 允许离线/测试兜底
    if os.getenv("DAILY_BRIEF_DISABLE_LLM") == "1":
        return [
            "今天内容中最关键的一个概念是什么？你能用自己的话复述吗？",
            "这些知识点之间的因果/依赖关系是什么？",
            "你能把其中一个方法应用到自己的学习/工作场景里吗？",
        ][:count]

    system_prompt = f"""
你是一位善于启发思考的学习教练。

请基于用户的每日学习简报，生成 {count} 条“引导性思考题”（prompt questions），用于放在前端简报正文后。

要求：
1) 每条问题 20~45 个汉字左右
2) 避免是死记硬背；更偏向反思、迁移、应用、对比、例证
3) 用中文输出
4) 只输出纯 JSON，不要 Markdown

输出格式：
{{
  "prompt_questions": ["问题1", "问题2", "问题3"]
}}
"""

    user_msg = f"""【封面摘要】
{posterior_insight}

【简报正文】
{key_concepts}
"""

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
        )
        obj = json.loads(response.choices[0].message.content)
        items = obj.get("prompt_questions")
        if not isinstance(items, list):
            raise ValueError("prompt_questions not a list")
        cleaned: list[str] = []
        for q in items:
            if not isinstance(q, str):
                continue
            q = q.strip()
            if q:
                cleaned.append(q)
        if not cleaned:
            raise ValueError("empty prompt_questions")
        return cleaned[:count]
    except Exception:
        return [
            "今天内容中最关键的一个概念是什么？你能用自己的话复述吗？",
            "这些知识点之间的因果/依赖关系是什么？",
            "你能把其中一个方法应用到自己的学习/工作场景里吗？",
        ][:count]


def generate_daily_brief_for_db(
    *,
    user_id: int,
    handouts: list[dict],
    origin: str = "PDF",
    prompt_questions_count: int = 3,
) -> dict:
    """从给定 handouts 直接生成“数据库字段对齐”的每日简报 payload。

    返回字段贴合你提供的 daily_briefs 表结构（不依赖扫描目录）：
    {
      "user_id": int,
      "posterior_insight": str,
      "key_concepts": str,
      "created_at": str,
      "review_stage": int,
      "User_reflect": str,
      "source_handouts": str,
      "origin": "SC"|"PDF",
      "prompt_question": str,
      "prompt_questions": list[str]
    }

    说明：DB 若只有 prompt_question 单列，可把 prompt_questions 用换行/JSON 序列化后存入。
    """
    if not handouts:
        raise ValueError("handouts 不能为空")

    # 1) 合成简报正文
    target_date = datetime.now().strftime("%Y-%m-%d")
    briefing_content = generate_briefing_from_handouts(handouts, target_date)

    posterior_insight = briefing_content.get("posterior_insight", "")
    key_concepts = briefing_content.get("key_concepts", "")

    # DB 里 posterior_insight 是 String(100)，这里做一下安全截断
    posterior_insight = _truncate_chars(posterior_insight, 100)

    # 2) 生成引导性思考题
    prompt_questions = generate_prompt_questions(
        posterior_insight=posterior_insight,
        key_concepts=key_concepts,
        count=prompt_questions_count,
    )
    prompt_question = "\n".join(prompt_questions)

    # 3) source_handouts：DB 是 String(100)，这里用标题拼接并截断
    titles = [h.get("meta", {}).get("title", "未知") for h in handouts]
    source_handouts = _truncate_chars(" / ".join(titles), 100)

    created_at = datetime.now(timezone.utc).isoformat()
    return {
        "user_id": user_id,
        "posterior_insight": posterior_insight,
        "key_concepts": key_concepts,
        "created_at": created_at,
        "review_stage": 0,
        "User_reflect": "",
        "source_handouts": source_handouts,
        "origin": origin,
        "prompt_question": prompt_question,
        "prompt_questions": prompt_questions,
    }


def _extract_pdf_text_with_pages(pdf_path: str, max_pages: int = 30) -> str:
    """从 PDF 提取文本并尽量保留页结构。"""

    try:
        import fitz  # PyMuPDF
    except Exception as e:
        raise RuntimeError(f"缺少 PDF 解析依赖 PyMuPDF(fitz): {e}")

    try:
        doc = fitz.open(pdf_path)
        pages_text: list[str] = []
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            text = page.get_text("text")
            if text and text.strip():
                pages_text.append(f"[第 {i + 1} 页]\n{text}")
        return "\n\n".join(pages_text).strip()
    except Exception as e:
        raise RuntimeError(f"无法从 PDF 中提取文字: {e}")


def generate_briefing_from_pdf_text(
    *,
    title: str,
    text: str,
    target_date: str,
) -> dict:
    """直接基于 PDF 原文生成每日简报（不经过讲义结构化）。

    返回：{"posterior_insight": str, "key_concepts": str}
    """

    if not (text or "").strip():
        raise ValueError("PDF 文本为空")

    # 离线/测试兜底：直接用原文裁剪拼接
    if os.getenv("DAILY_BRIEF_DISABLE_LLM") == "1":
        cleaned = "\n".join([ln.strip() for ln in text.splitlines() if ln.strip()])
        snippet = _truncate_chars(cleaned, 1800)
        posterior_insight = _truncate_chars(
            f"《{title}》聚焦于相关核心概念与方法。建议先抓住关键词，再围绕问题-方法-结论做结构化复盘。",
            100,
        )
        key_concepts = (
            f"1. 今日学习总览\n材料：{title}\n\n"
            f"2. 原文要点（节选）\n{snippet}\n\n"
            "3. 学习建议\n- 提炼3个关键词并各写一句解释\n- 找到一条可迁移到自己场景的应用路径\n"
        )
        return {"posterior_insight": posterior_insight, "key_concepts": key_concepts}

    system_prompt = f"""
你是一位资深知识整合师。今天是 {target_date}。

请基于用户上传的 PDF 原文内容，生成一篇**每日学习简报**。

输出必须是纯 JSON，结构如下，不要包含任何 Markdown 代码块：

{{
    "posterior_insight": "封面摘要：约150字，使用专业、简洁的第三人称陈述语气，概括这份材料的核心主题、覆盖范围与最重要的方法/结论，适合作为简报封面的内容摘要",
    "key_concepts": "简报全文：包含以下部分：\\n1. 今日学习总览（介绍材料主题）\\n2. 核心知识点梳理（提炼3-7个核心概念并简要解释）\\n3. 内在逻辑与洞见（概念之间的关系/推导链路/取舍条件）\\n4. 今日学习建议（1-2条，复习/应用提示）\\n全文不少于500字，段落清晰"
}}
"""

    user_msg = f"""材料标题：{title}

以下是 PDF 原文（可能包含页码标记）：

{(text or "")[:45000]}
"""

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
        )
        raw = response.choices[0].message.content
        return json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"LLM 调用失败: {e}")


def process_pdf_to_daily_brief_for_db(
    *,
    pdf_path: str,
    filename: str,
    user_id: int,
    origin: str = "PDF",
    prompt_questions_count: int = 3,
    max_pages: int = 30,
) -> dict:
    """上传 PDF 后直接生成“数据库字段对齐”的每日简报 payload（不经过讲义）。"""

    title = os.path.splitext(os.path.basename(filename or "upload.pdf"))[0] or "未知"
    text = _extract_pdf_text_with_pages(pdf_path, max_pages=max_pages)

    target_date = datetime.now().strftime("%Y-%m-%d")
    briefing_content = generate_briefing_from_pdf_text(
        title=title,
        text=text,
        target_date=target_date,
    )

    posterior_insight = _truncate_chars(briefing_content.get("posterior_insight", ""), 100)
    key_concepts = briefing_content.get("key_concepts", "")

    prompt_questions = generate_prompt_questions(
        posterior_insight=posterior_insight,
        key_concepts=key_concepts,
        count=prompt_questions_count,
    )
    prompt_question = "\n".join(prompt_questions)

    source_handouts = _truncate_chars(title, 100)
    created_at = datetime.now(timezone.utc).isoformat()

    return {
        "user_id": user_id,
        "posterior_insight": posterior_insight,
        "key_concepts": key_concepts,
        "created_at": created_at,
        "review_stage": 0,
        "User_reflect": "",
        "source_handouts": source_handouts,
        "origin": origin,
        "prompt_question": prompt_question,
        "prompt_questions": prompt_questions,
    }


def load_latest_handout_from_storage(*, source_file: str | None = None, handout_filename: str | None = None) -> dict:
    """从 data/handouts 中读取讲义 JSON。

    用途：当客户端不再上传 PDF，而是希望基于已存储讲义生成简报时使用。

    参数：
    - handout_filename: 例如 "upload_handout.json"（优先）
    - source_file: 例如 "upload.pdf"，将匹配 meta.source_file
    """

    if handout_filename:
        fname = os.path.basename(handout_filename)
        path = handout_filename if os.path.isabs(handout_filename) else os.path.join(HANDOUT_DIR, fname)
        if not os.path.exists(path):
            raise FileNotFoundError(f"未找到讲义文件: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("讲义内容不是合法 JSON 对象")
        return data

    if not source_file:
        # 不提供任何定位信息时，默认取最新的一份讲义（按修改时间）
        if not os.path.isdir(HANDOUT_DIR):
            raise FileNotFoundError(f"讲义目录不存在: {HANDOUT_DIR}")

        candidates = [
            os.path.join(HANDOUT_DIR, fn)
            for fn in os.listdir(HANDOUT_DIR)
            if fn.endswith("_handout.json")
        ]
        if not candidates:
            raise FileNotFoundError(f"讲义目录为空: {HANDOUT_DIR}")

        latest_path = max(candidates, key=os.path.getmtime)
        with open(latest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("讲义内容不是合法 JSON 对象")
        return data

    if not os.path.isdir(HANDOUT_DIR):
        raise FileNotFoundError(f"讲义目录不存在: {HANDOUT_DIR}")

    candidates: list[str] = []
    for fname in os.listdir(HANDOUT_DIR):
        if not fname.endswith("_handout.json"):
            continue
        fpath = os.path.join(HANDOUT_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                obj = json.load(f)
            meta_source = (obj.get("meta", {}) or {}).get("source_file", "")
            if meta_source == source_file or os.path.basename(meta_source) == os.path.basename(source_file):
                candidates.append(fpath)
        except Exception:
            continue

    if not candidates:
        raise FileNotFoundError(f"未找到与 source_file 匹配的讲义: {source_file}")

    latest_path = max(candidates, key=os.path.getmtime)
    with open(latest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("讲义内容不是合法 JSON 对象")
    return data


def process_handout_to_daily_brief_for_db(
    *,
    handout: dict,
    user_id: int,
    origin: str = "PDF",
    prompt_questions_count: int = 3,
) -> dict:
    """基于已存储讲义直接生成 DB 对齐简报 payload。"""

    return generate_daily_brief_for_db(
        user_id=user_id,
        handouts=[handout],
        origin=origin,
        prompt_questions_count=prompt_questions_count,
    )


def save_daily_brief_payload(*, payload: dict, user_id: int) -> str:
    """将“完整简报 payload”保存到 data/daily_briefs/ 并返回路径。"""

    os.makedirs(DAILY_BRIEFS_DIR, exist_ok=True)

    # 落盘前：尝试写入 Learning_DB，并回填 daily_brief_id
    try:
        if isinstance(payload, dict):
            payload.setdefault("user_id", user_id)
            payload.setdefault("origin", payload.get("origin") or "PDF")
            payload.setdefault("User_reflect", payload.get("User_reflect") or payload.get("user_reflect") or "")
            daily_brief_id = _try_persist_daily_brief_to_learning_db_api(payload)
            if daily_brief_id is not None:
                payload["daily_brief_id"] = daily_brief_id
    except Exception:
        pass

    day = datetime.now().strftime("%Y-%m-%d")
    ts = int(time.time())
    path = os.path.join(DAILY_BRIEFS_DIR, f"brief_{day}_user{user_id}_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def to_minimal_daily_brief_response(*, payload: dict) -> dict:
    """将完整 payload 裁剪为接口最小返回结构。"""

    prompt_questions = payload.get("prompt_questions")
    if not isinstance(prompt_questions, list):
        prompt_questions = []
    prompt_questions = [q for q in prompt_questions if isinstance(q, str) and q.strip()]

    return {
        "posterior_insight": payload.get("posterior_insight", ""),
        "key_concepts": payload.get("key_concepts", ""),
        "prompt_questions": prompt_questions,
        "created_at": payload.get("created_at") or "",
        "updated_at": payload.get("updated_at") or "",
    }


# ─────────────────────────────────────────────
# 以下为每日简报「更新」相关函数
# ─────────────────────────────────────────────

def load_daily_briefing(user_id: int, target_date: str = None) -> dict:
    """
    从 data/daily_briefs/ 读取指定日期的简报 JSON。
    找不到则抛出 FileNotFoundError。
    """
    if target_date is None:
        target_date = datetime.now().strftime("%Y-%m-%d")

    path = _find_daily_brief_path(user_id=user_id, target_date=target_date)

    with open(path, "r", encoding="utf-8") as f:
        briefing = json.load(f)

    # 兼容旧文件：若缺少 prompt_questions，则回填并覆盖保存
    need_backfill = not isinstance(briefing, dict) or not isinstance(briefing.get("prompt_questions"), list)
    if need_backfill and isinstance(briefing, dict):
        prompt_questions = generate_prompt_questions(
            posterior_insight=briefing.get("posterior_insight", ""),
            key_concepts=briefing.get("key_concepts", ""),
            count=3,
        )
        briefing["prompt_questions"] = prompt_questions
        briefing["prompt_question"] = "\n".join(prompt_questions)
        with open(path, "w", encoding="utf-8") as wf:
            json.dump(briefing, wf, ensure_ascii=False, indent=2)

    return briefing


def _update_briefing_via_llm(original: dict, user_reflect: str) -> dict:
    """
    调用 LLM，将用户补充内容融入原简报，返回更新后的 posterior_insight 和 key_concepts。
    """
    target_date = original.get("target_date", "")
    source_handouts = _normalize_source_handouts(original.get("source_handouts", ""))

    system_prompt = f"""
你是一位专业的知识整合师。用户今天（{target_date}）生成了一份基于讲义《{source_handouts}》的学习简报，
现在用户补充了自己的学习心得与思考，请将两者融合，输出一份更新后的简报。

要求：
1. 保持专业、简洁的第三人称陈述语气，不要出现"我"字
2. posterior_insight 约150字，需融入用户补充的关键个人洞见或疑问，体现个人学习深度
3. key_concepts 为完整更新简报，在原有结构基础上新增"用户思考与延伸"章节，将用户反思内容融入分析，不少于500字
4. 只返回纯 JSON，不要 Markdown 代码块

输出格式：
{{
    "posterior_insight": "更新后的封面摘要（约150字）",
    "key_concepts": "更新后的简报全文（不少于500字）"
}}
"""

    user_msg = f"""原简报封面摘要：
{original.get('posterior_insight', '')}

原简报全文：
{original.get('key_concepts', '')}

用户补充内容：
{user_reflect}

请融合以上内容，生成更新后的简报。"""

    # 离线/测试兜底：不调用 LLM 也能跑通更新流程
    if os.getenv("DAILY_BRIEF_DISABLE_LLM") == "1":
        original_pi = (original.get("posterior_insight", "") or "").strip()
        original_kc = (original.get("key_concepts", "") or "").strip()
        reflect = (user_reflect or "").strip()

        merged_pi = original_pi
        if reflect:
            merged_pi = _truncate_chars(f"{original_pi}（用户补充：{reflect}）", 100)

        merged_kc = original_kc
        if reflect:
            merged_kc = (
                f"{original_kc}\n\n"
                "用户思考与延伸\n"
                f"{reflect}\n"
            )

        return {"posterior_insight": merged_pi, "key_concepts": merged_kc}

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        raise RuntimeError(f"LLM 调用失败: {e}")


def update_daily_briefing(user_id: int, user_reflect: str, target_date: str = None) -> dict:
    """
    更新每日简报主函数。

    流程：加载原简报 → LLM 融合用户反思 → 覆盖保存 → 返回更新结果

    Args:
        user_id:      用户 ID
        user_reflect: 用户在手机端输入的补充内容/心得
        target_date:  目标日期，默认今天

    Returns:
        与 generate_daily_briefing 格式完全一致的 dict，额外增加：
        - "updated_at": 本次更新时间
        - "user_reflect": 用户补充内容（已写入）
    """
    if target_date is None:
        target_date = datetime.now().strftime("%Y-%m-%d")

    start_time = time.time()

    # 1. 加载原简报（兼容旧/新命名）
    briefing_path = _find_daily_brief_path(user_id=user_id, target_date=target_date)
    with open(briefing_path, "r", encoding="utf-8") as f:
        briefing = json.load(f)

    if not isinstance(briefing, dict):
        raise ValueError("简报内容不是合法 JSON 对象")

    # 2. LLM 融合更新
    updated_content = _update_briefing_via_llm(briefing, user_reflect)

    # 3. 更新字段：review_stage 递增（兼容 int/str），next_review_date 若存在则同步更新
    try:
        old_stage = int(briefing.get("review_stage", 0))
    except Exception:
        old_stage = 0
    new_stage = old_stage + 1

    # next_review_date 从本次复习日期起算，按新 stage 对应的间隔天数推算
    # 若已超过最大阶段，保持最大间隔（120天）无限复习
    today = datetime.now().strftime("%Y-%m-%d")
    interval = EBBINGHAUS_INTERVALS[min(new_stage, len(EBBINGHAUS_INTERVALS) - 1)]
    next_review_date = (
        datetime.strptime(today, "%Y-%m-%d") + timedelta(days=interval)
    ).strftime("%Y-%m-%d")

    updated_at = datetime.now(timezone.utc).isoformat()
    briefing["posterior_insight"] = updated_content.get("posterior_insight", briefing.get("posterior_insight", ""))
    briefing["key_concepts"] = updated_content.get("key_concepts", briefing.get("key_concepts", ""))

    # 更新后重新生成引导性思考题
    prompt_questions = generate_prompt_questions(
        posterior_insight=briefing.get("posterior_insight", ""),
        key_concepts=briefing.get("key_concepts", ""),
        count=3,
    )
    briefing["prompt_questions"] = prompt_questions
    briefing["prompt_question"] = "\n".join(prompt_questions)

    # 新格式字段名（与你给的 JSON 一致）：User_reflect
    briefing["User_reflect"] = user_reflect
    # 兼容旧字段名：user_reflect
    briefing["user_reflect"] = user_reflect
    briefing["review_stage"] = new_stage
    if "next_review_date" in briefing:
        briefing["next_review_date"] = next_review_date
    briefing["updated_at"] = updated_at
    briefing["process_time"] = f"{time.time() - start_time:.2f}s"

    # 4) 尽量把 payload 对齐到“新简报 DB 格式”所需字段（不强制删除旧字段）
    briefing.setdefault("user_id", user_id)
    briefing.setdefault("origin", briefing.get("origin", "PDF"))
    # 兼容旧：source_handouts 可能是 list；新格式希望是 str
    briefing["source_handouts"] = _truncate_chars(
        _normalize_source_handouts(briefing.get("source_handouts", "")),
        100,
    )
    # created_at 缺失时补齐
    briefing.setdefault("created_at", datetime.now(timezone.utc).isoformat())

    # 5. 覆盖保存原文件（写回原路径，避免丢失 ts 命名）
    with open(briefing_path, "w", encoding="utf-8") as f:
        json.dump(briefing, f, ensure_ascii=False, indent=2)
    print(f"💾 简报已更新并保存: {briefing_path}")
    print(f"📅 review_stage: {old_stage} → {new_stage}，下次复习日期: {next_review_date}")

    briefing["archived_at"] = briefing_path

    return briefing


def get_briefs_to_review(user_id: int, check_date: str = None) -> dict | None:
    """
    扫描用户所有历史简报，返回今天（或指定日期）最需要复习的那一份。
    匹配规则：next_review_date <= check_date，按逾期天数取最大值的一条。

    Returns:
        dict 或 None（无待复习简报时返回 None），包含：
        {
            "target_date":      简报所属日期,
            "review_stage":     当前阶段,
            "next_review_date": 原定复习日期,
            "overdue_days":     逾期天数（0=今天正好到期）,
            "posterior_insight":封面摘要,
            "source_handouts":  来源讲义
        }
    """
    if check_date is None:
        check_date = datetime.now().strftime("%Y-%m-%d")

    best = None  # 记录逾期天数最多的那一条
    if not os.path.isdir(DAILY_BRIEFS_DIR):
        return None

    # 兼容两种落盘命名：
    # - 旧：brief_{target_date}_user{user_id}.json
    # - 新：brief_{target_date}_user{user_id}_{ts}.json
    patterns = [
        os.path.join(DAILY_BRIEFS_DIR, f"brief_*_user{user_id}.json"),
        os.path.join(DAILY_BRIEFS_DIR, f"brief_*_user{user_id}_*.json"),
    ]
    candidates: list[str] = []
    for pat in patterns:
        candidates.extend([p for p in glob.glob(pat) if os.path.isfile(p)])

    # 去重，保持稳定顺序
    seen: set[str] = set()
    candidates = [p for p in candidates if not (p in seen or seen.add(p))]

    for fpath in candidates:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)

            next_review = data.get("next_review_date", "")
            if not next_review:
                continue

            # next_review_date <= check_date 即需要复习
            if next_review <= check_date:
                check_dt = datetime.strptime(check_date, "%Y-%m-%d")
                review_dt = datetime.strptime(next_review, "%Y-%m-%d")
                overdue_days = (check_dt - review_dt).days

                candidate = {
                    "target_date": data.get("target_date", ""),
                    "review_stage": data.get("review_stage", 0),
                    "next_review_date": next_review,
                    "overdue_days": overdue_days,
                    "posterior_insight": data.get("posterior_insight", ""),
                    "source_handouts": data.get("source_handouts", []),
                }
                if best is None or overdue_days > best["overdue_days"]:
                    best = candidate
        except Exception as e:
            print(f"⚠️ 读取简报失败 {os.path.basename(fpath)}: {e}")

    return best
