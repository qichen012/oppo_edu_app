import os
import json
import time
from datetime import datetime, timezone, timedelta
from openai import OpenAI
from .config import ZHIZENGZENG_API_KEY, ZHIZENGZENG_BASE_URL, MODEL_NAME, OUTPUT_DIR

# 初始化客户端
client = OpenAI(api_key=ZHIZENGZENG_API_KEY, base_url=ZHIZENGZENG_BASE_URL)

# 讲义存储目录（与 lecture_handout_generator 保持一致）
HANDOUT_DIR = os.path.join(os.path.dirname(OUTPUT_DIR), "handouts")

# 每日简报存储目录
DAILY_BRIEFS_DIR = os.path.join(os.path.dirname(OUTPUT_DIR), "daily_briefs")
os.makedirs(DAILY_BRIEFS_DIR, exist_ok=True)

# Ebbinghaus 各阶段距下次复习的天数间隔
EBBINGHAUS_INTERVALS = [1, 2, 4, 7, 15, 30, 60, 120]  # stage 0->1 间隔1天, 依此类推


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
              "source_handouts": source_titles,
              "handout_count": len(handouts),
              "process_time": f"{time.time() - start_time:.2f}s",
              }

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

    path = os.path.join(DAILY_BRIEFS_DIR, f"brief_{target_date}_user{user_id}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"未找到简报文件: {path}，请先生成今日简报")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _update_briefing_via_llm(original: dict, user_reflect: str) -> dict:
    """
    调用 LLM，将用户补充内容融入原简报，返回更新后的 posterior_insight 和 key_concepts。
    """
    target_date = original.get("target_date", "")
    source_handouts = "、".join(original.get("source_handouts", []))

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

    # 1. 加载原简报
    briefing = load_daily_briefing(user_id, target_date)

    # 2. LLM 融合更新
    updated_content = _update_briefing_via_llm(briefing, user_reflect)

    # 3. 更新字段：review_stage 递增，重新计算 next_review_date
    old_stage = briefing.get("review_stage", 0)
    new_stage = old_stage + 1

    # next_review_date 从本次复习日期起算，按新 stage 对应的间隔天数推算
    # 若已超过最大阶段，保持最大间隔（120天）无限复习
    today = datetime.now().strftime("%Y-%m-%d")
    interval = EBBINGHAUS_INTERVALS[min(new_stage, len(EBBINGHAUS_INTERVALS) - 1)]
    next_review_date = (
        datetime.strptime(today, "%Y-%m-%d") + timedelta(days=interval)
    ).strftime("%Y-%m-%d")

    updated_at = datetime.now(timezone.utc).isoformat()
    briefing["posterior_insight"] = updated_content.get("posterior_insight", briefing["posterior_insight"])
    briefing["key_concepts"] = updated_content.get("key_concepts", briefing["key_concepts"])
    briefing["user_reflect"] = user_reflect
    briefing["review_stage"] = new_stage
    briefing["next_review_date"] = next_review_date
    briefing["updated_at"] = updated_at
    briefing["process_time"] = f"{time.time() - start_time:.2f}s"

    # 4. 覆盖保存原文件
    save_path = os.path.join(DAILY_BRIEFS_DIR, f"brief_{target_date}_user{user_id}.json")
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(briefing, f, ensure_ascii=False, indent=2)
    print(f"💾 简报已更新并保存: {save_path}")
    print(f"📅 review_stage: {old_stage} → {new_stage}，下次复习日期: {next_review_date}")

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

    prefix = f"brief_"
    suffix = f"_user{user_id}.json"

    for fname in os.listdir(DAILY_BRIEFS_DIR):
        if not (fname.startswith(prefix) and fname.endswith(suffix)):
            continue
        fpath = os.path.join(DAILY_BRIEFS_DIR, fname)
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
            print(f"⚠️ 读取简报失败 {fname}: {e}")

    return best
