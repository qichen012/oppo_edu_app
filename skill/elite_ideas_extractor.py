"""Elite Ideas 提取器。

当前支持两种来源：
- PDF：用于兼容旧流程（`process_pdf_to_elite_ideas`）
- 已落盘讲义（handout JSON）：用于新流程（`process_handout_to_elite_ideas`）

约束：每份讲义固定产出 2 条 Elite Ideas（用于 elite_idea_cards 表）。
"""
import os
import time
import json
import base64
import hashlib
import requests
import fitz  # PyMuPDF
from openai import OpenAI
from datetime import datetime
from .config import ZHIZENGZENG_API_KEY, ZHIZENGZENG_BASE_URL, MODEL_NAME, OUTPUT_DIR


# 初始化客户端
client = OpenAI(api_key=ZHIZENGZENG_API_KEY, base_url=ZHIZENGZENG_BASE_URL)

# 项目根目录（用于将落盘路径与启动 cwd 解耦）
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# 讲义存储目录（与 lecture_handout_generator / daily_briefing_generator 保持一致）
# 说明：历史上这里依赖相对路径（受启动 cwd 影响）；改为绝对路径提升稳定性。
HANDOUT_DIR = os.path.join(PROJECT_ROOT, "data", "handouts")

# Elite Ideas 落盘目录（独立于其它 processed_notes 输出）
ELITE_IDEAS_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "elite_ideas")
os.makedirs(ELITE_IDEAS_OUTPUT_DIR, exist_ok=True)

# Elite Ideas 文生图落盘目录
ELITE_IDEAS_IMAGE_DIR = os.path.join(ELITE_IDEAS_OUTPUT_DIR, "images")
os.makedirs(ELITE_IDEAS_IMAGE_DIR, exist_ok=True)


# Elite Ideas 系统提示词
ELITE_IDEAS_SYSTEM_PROMPT = """你是一位见识卓越的学者与思想家，精通从各类学科知识中提炼底层智慧。
你的任务是帮助一位正在接受高等教育的学生，从他的课程讲义中发现知识背后真正有价值的"Meta Ideas"与"Elite Ideas"——
也就是超越学科本身、具有跨领域迁移价值的深层洞见与思维范式。

【分析框架】
你可以从但不限于以下维度挖掘：
1. 工程思维与系统设计哲学（如：以冗余换稳定、用局部信息重建全局等）
2. 金融与投资决策准则（如：信息不对称的利用、不确定性下的最优策略等）
3. 博弈论与竞争策略（如：纳什均衡背后的协作逻辑等）
4. 一个学科/技术领域的发展脉络与底层逻辑
5. 认知与决策科学（如：压缩即理解、模型即偏见等）
6. 哲学层面的世界观洞见

【输出要求】
- 每条 Elite Idea 需包含：
  ① 【标题】简洁有力的洞见标题（一句话）
  ② 【讲义来源】对应讲义中的哪个知识点/概念（简要）
  ③ 【洞见阐释】深入解释这条智慧的内涵，并结合 1-2 个跨领域类比或应用场景
  ④ 【迁移域】这条智慧可迁移至哪些领域（如：投资、管理、创业、人际等）
- 共输出 2 条 Elite Ideas，按重要性或启发性排序
- 语言：中文，风格：深刻但不晦涩

【重要提示】
请基于讲义实际内容进行分析，不要泛泛而谈。每条洞见都必须有清晰的讲义知识点作为根基。"""


DB_JSON_SYSTEM_PROMPT = """你是一个严格的结构化信息提取器。
请将给定的 Elite Ideas 文本转换为 JSON，且只输出 JSON，不要输出任何额外文字。

JSON 结构要求：
{
    "elite_idea_cards": [
        {
            "origin_concept": "string",
            "meta_idea_name": "string",
            "meta_explanation": "string",
            "cases": [
                {
                    "case_title": "string",
                    "case_content": "string",
                    "image_path": "string",
                    "query_rewrite": "string"
                }
            ],
            "external_resources": [
                {
                    "title": "string",
                    "url": "string",
                    "LLM_context": "string",
                    "source": "string"
                }
            ]
        }
    ]
}

约束：
1) 保证字段名完全一致。
2) 缺失字段用空字符串。
3) cases 和 external_resources 必须始终为数组（可为空）。
4) 仅从输入内容提取，不要编造事实。"""


def extract_pdf_text(pdf_path: str, max_pages: int = None) -> str:
    """
    从 PDF 文件中提取文本内容
    
    Args:
        pdf_path: PDF 文件路径
        max_pages: 最大提取页数，None 表示提取所有页
    
    Returns:
        提取的文本内容
    """
    try:
        doc = fitz.open(pdf_path)
        all_text_parts = []
        
        total_pages = len(doc) if max_pages is None else min(len(doc), max_pages)
        
        for i in range(total_pages):
            page = doc[i]
            text = page.get_text().strip()
            if text:
                all_text_parts.append(f"【第 {i+1} 页】\n{text}")
        
        doc.close()
        
        full_text = "\n\n".join(all_text_parts)
        return full_text
        
    except Exception as e:
        raise Exception(f"PDF 文本提取失败: {str(e)}")


def extract_elite_ideas(text: str, max_tokens: int = 4096, temperature: float = 0.7) -> str:
    """
    使用 LLM 从讲义文本中提取 Elite Ideas
    
    Args:
        text: 讲义文本内容
        max_tokens: 最大生成 token 数
        temperature: 生成温度参数
        
    Returns:
        提取的 Elite Ideas 内容
    """
    try:
        user_prompt = f"""以下是我的课程讲义全文，请帮我挖掘其中有价值的 Elite Ideas：

{text}

请按照要求格式输出分析结果。"""
        
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": ELITE_IDEAS_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        result = response.choices[0].message.content
        return result
        
    except Exception as e:
        raise Exception(f"Elite Ideas 提取失败: {str(e)}")


def _truncate(value: str, max_len: int) -> str:
    if value is None:
        return ""
    value = str(value).strip()
    return value[:max_len]


def _should_generate_elite_ideas_images() -> bool:
    """是否启用 Elite Ideas 文生图。

    默认启用；离线/测试可通过环境变量关闭：
    - ELITE_IDEAS_DISABLE_T2I=1
    """

    return str(os.getenv("ELITE_IDEAS_DISABLE_T2I", "")).strip() != "1"


def _safe_image_basename(base_name: str) -> str:
    base_name = (base_name or "handout").strip()
    # 文件名尽量短且稳定（避免路径过长）
    cleaned = "".join(ch for ch in base_name if ch.isalnum() or ch in ("-", "_"))
    if not cleaned:
        cleaned = "handout"
    return cleaned[:48]


def _resolve_zhizengzeng_gemini_api_key() -> str:
    """获取智增增 Gemini 图片生成用的 key。

    文档示例使用 GEMINI_API_KEY，这里做几种兼容：
    - 优先环境变量 GEMINI_API_KEY
    - 其次环境变量 ZHIZENGZENG_GEMINI_API_KEY
    - 最后回退到 skill/config.py 里的 ZHIZENGZENG_API_KEY
    """

    for k in ("GEMINI_API_KEY", "ZHIZENGZENG_GEMINI_API_KEY"):
        v = str(os.getenv(k, "")).strip()
        if v:
            return v
    return str(ZHIZENGZENG_API_KEY or "").strip()


def _build_zhizengzeng_gemini_generate_url(*, model: str, api_key: str) -> str:
    """构造智增增 Google v1beta 的 generateContent URL。

    文档示例：
    https://api.zhizengzeng.com/google/v1beta/models/gemini-2.5-flash-image:generateContent?key=... 
    """

    base = "https://api.zhizengzeng.com/google/v1beta/models"
    model = (model or "").strip()
    if not model:
        model = "gemini-2.5-flash-image"

    # 允许用户传完整 URL 或者传带/不带后缀的 model
    if model.startswith("http://") or model.startswith("https://"):
        return model

    if model.startswith("models/"):
        model = model[len("models/"):]

    if model.endswith(":generateContent"):
        path = model
    else:
        path = f"{model}:generateContent"

    return f"{base}/{path}?key={api_key}"


def _mime_to_ext(mime: str) -> str:
    m = (mime or "").lower().strip()
    if m == "image/png":
        return ".png"
    if m in {"image/jpg", "image/jpeg"}:
        return ".jpg"
    if m == "image/webp":
        return ".webp"
    return ".png"


def _parse_target_size(value: str, default: tuple[int, int] = (1080, 480)) -> tuple[int, int]:
    """Parse size string like '1080x480' to (w, h)."""

    raw = str(value or "").lower().strip()
    if not raw:
        return default
    if "x" not in raw:
        return default
    w_s, h_s = raw.split("x", 1)
    try:
        w = int(w_s.strip())
        h = int(h_s.strip())
        if w > 0 and h > 0:
            return w, h
    except Exception:
        pass
    return default


def _resize_cover_center_png(img_bytes: bytes, *, target_w: int, target_h: int) -> bytes:
    """Resize with cover strategy (keep aspect ratio) and center-crop to exact size.

    Returns PNG bytes.
    """

    try:
        from PIL import Image  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Pillow is required for resizing images to 1080x480. "
            "Please install Pillow (pip install Pillow)."
        ) from e

    from io import BytesIO

    with Image.open(BytesIO(img_bytes)) as im:
        im = im.convert("RGBA")
        src_w, src_h = im.size
        if src_w <= 0 or src_h <= 0:
            raise RuntimeError("Invalid source image size")

        scale = max(target_w / src_w, target_h / src_h)
        new_w = int(round(src_w * scale))
        new_h = int(round(src_h * scale))

        resized = im.resize((new_w, new_h), resample=Image.LANCZOS)

        left = max(0, (new_w - target_w) // 2)
        top = max(0, (new_h - target_h) // 2)
        cropped = resized.crop((left, top, left + target_w, top + target_h))

        out = BytesIO()
        cropped.save(out, format="PNG")
        return out.getvalue()


def _fallback_pattern_png(*, seed: str, target_w: int, target_h: int) -> bytes:
    """本地兜底：生成一张确定性图案 PNG（不依赖外网文生图）。

    用于网络/代理不可用时，仍然保证每个 case 都有一张可展示图片。
    """

    try:
        from PIL import Image, ImageDraw  # type: ignore
    except Exception as e:
        raise RuntimeError("Pillow is required for fallback image generation") from e

    h = hashlib.sha1((seed or "").encode("utf-8")).digest()

    def _c(i: int) -> tuple[int, int, int]:
        # 生成较亮的颜色，避免过暗
        r = 80 + (h[i % len(h)] % 176)
        g = 80 + (h[(i + 3) % len(h)] % 176)
        b = 80 + (h[(i + 7) % len(h)] % 176)
        return int(r), int(g), int(b)

    img = Image.new("RGB", (target_w, target_h), (245, 245, 245))
    draw = ImageDraw.Draw(img)

    # 画几块矩形/条纹，确保每个 seed 不同图案不同
    blocks = 7
    for i in range(blocks):
        x0 = int((h[i] / 255) * target_w)
        y0 = int((h[(i + 1) % len(h)] / 255) * target_h)
        w = int((0.18 + (h[(i + 2) % len(h)] / 255) * 0.35) * target_w)
        hh = int((0.12 + (h[(i + 4) % len(h)] / 255) * 0.25) * target_h)
        x1 = max(0, min(target_w, x0 + w))
        y1 = max(0, min(target_h, y0 + hh))
        x0 = max(0, min(target_w, x0))
        y0 = max(0, min(target_h, y0))
        if x1 <= x0 or y1 <= y0:
            continue
        draw.rectangle([x0, y0, x1, y1], fill=_c(i))

    from io import BytesIO

    out = BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _generate_elite_idea_image(*, prompt: str, model: str) -> tuple[bytes, str]:
    """调用智增增 Google v1beta generateContent，返回 (图片bytes, mimeType)。"""

    api_key = _resolve_zhizengzeng_gemini_api_key()
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY (or ZHIZENGZENG_GEMINI_API_KEY)")

    url = _build_zhizengzeng_gemini_generate_url(model=model, api_key=api_key)

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
            ]
        }],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
        },
    }

    r = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=120)
    if r.status_code >= 400:
        raise RuntimeError(f"T2I http {r.status_code}: {r.text[:500]}")

    obj = r.json() if r.content else {}
    candidates = obj.get("candidates") if isinstance(obj, dict) else None
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError("T2I response missing candidates")

    content = (candidates[0] or {}).get("content") if isinstance(candidates[0], dict) else None
    parts = (content or {}).get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list) or not parts:
        raise RuntimeError("T2I response missing content.parts")

    inline = None
    for p in parts:
        if isinstance(p, dict) and isinstance(p.get("inlineData"), dict):
            inline = p["inlineData"]
            break
    if not inline:
        raise RuntimeError("T2I response missing inlineData")

    mime = str(inline.get("mimeType", "image/png") or "image/png")
    data_b64 = inline.get("data")
    if not data_b64:
        raise RuntimeError("T2I response inlineData missing data")

    try:
        img_bytes = base64.b64decode(data_b64)
    except Exception as e:
        raise RuntimeError(f"T2I base64 decode failed: {e}")

    if not img_bytes:
        raise RuntimeError("T2I produced empty image bytes")

    return img_bytes, mime


def _maybe_generate_images_for_cards(*, base_name: str, cards: list[dict]) -> None:
    """为每条 elite_idea_card 生成一张图，并将相对路径写回 card['image_path']。

    - 使用 meta_idea_name 作为主要依据
    - 图片落盘到 data/elite_ideas/images
    - 失败不阻断主流程（只是不带图）
    """

    if not _should_generate_elite_ideas_images():
        return

    if not isinstance(cards, list) or not cards:
        return

    # 对齐智增增文档：默认走 gemini-2.5-flash-image:generateContent
    image_model = str(os.getenv("ELITE_IDEAS_T2I_MODEL", "gemini-2.5-flash-image")).strip() or "gemini-2.5-flash-image"

    # 输出图片最终规格（默认 1080x480）
    target_w, target_h = _parse_target_size(os.getenv("ELITE_IDEAS_T2I_OUT_SIZE", "1080x480"), default=(1080, 480))

    base_stub = _safe_image_basename(base_name)

    for idx, card in enumerate(cards):
        if not isinstance(card, dict):
            continue

        # 已有图片则不重复生成
        if str(card.get("image_path", "") or "").strip():
            continue

        meta_idea_name = str(card.get("meta_idea_name", "") or "").strip()
        if not meta_idea_name:
            continue

        # 用 meta_idea_name 构造提示词（按你的要求：以它为依据）
        prompt = (
            "请根据下面的‘元想法标题’生成一张能表达其含义的概念插画（不需要文字水印），风格简洁、清晰、适合做知识卡片配图。\n\n"
            f"元想法标题：{meta_idea_name}"
        )

        # 用 hash 让文件名稳定且短
        h = hashlib.sha1(meta_idea_name.encode("utf-8")).hexdigest()[:10]
        try:
            img_bytes, mime = _generate_elite_idea_image(prompt=prompt, model=image_model)
            # 强制输出为指定规格（等比缩放 + 居中裁剪），并统一保存为 PNG
            img_bytes = _resize_cover_center_png(img_bytes, target_w=target_w, target_h=target_h)
            mime = "image/png"
            ext = _mime_to_ext(mime)
            filename = f"{base_stub}_card{idx+1}_{h}{ext}"
            abs_path = os.path.join(ELITE_IDEAS_IMAGE_DIR, filename)
            with open(abs_path, "wb") as f:
                f.write(img_bytes)

            # 写回相对路径（从项目根目录起）
            rel_path = os.path.relpath(abs_path, PROJECT_ROOT)
            card["image_path"] = rel_path.replace(os.sep, "/")
        except Exception:
            # 文生图失败不阻断主流程
            continue


def _maybe_generate_images_for_cases(*, base_name: str, cases: list[dict]) -> None:
    """为每条 elite_idea_case 生成一张图，并将相对路径写回 case['image_path']。

    - 使用 case_title + case_content 作为主要依据
    - 图片落盘到 data/elite_ideas/images
    - 失败不阻断主流程（只是不带图）
    """

    if not _should_generate_elite_ideas_images():
        return

    if not isinstance(cases, list) or not cases:
        return

    image_model = str(os.getenv("ELITE_IDEAS_T2I_MODEL", "gemini-2.5-flash-image")).strip() or "gemini-2.5-flash-image"
    target_w, target_h = _parse_target_size(os.getenv("ELITE_IDEAS_T2I_OUT_SIZE", "1080x480"), default=(1080, 480))

    base_stub = _safe_image_basename(base_name)

    for idx, case in enumerate(cases):
        if not isinstance(case, dict):
            continue

        # 已有图片且文件存在则不重复生成
        existing = str(case.get("image_path", "") or "").strip()
        if existing:
            abs_existing = os.path.join(PROJECT_ROOT, existing.replace("/", os.sep))
            if os.path.exists(abs_existing):
                continue

        title = str(case.get("case_title", "") or "").strip()
        content = str(case.get("case_content", "") or "").strip()
        if not title and not content:
            continue

        prompt = (
            "请根据下面的‘案例标题’和‘案例内容’生成一张能表达其含义的概念插画（不需要文字水印），风格简洁、清晰、适合做知识卡片配图。\n\n"
            f"案例标题：{title}\n"
            f"案例内容：{content}"
        )

        # 用 hash 让文件名稳定且短
        h_src = (title + "\n" + content).encode("utf-8")
        h = hashlib.sha1(h_src).hexdigest()[:10]
        ext = ".png"
        filename = f"{base_stub}_case{idx+1}_{h}{ext}"
        abs_path = os.path.join(ELITE_IDEAS_IMAGE_DIR, filename)

        try:
            img_bytes, mime = _generate_elite_idea_image(prompt=prompt, model=image_model)
            try:
                img_bytes = _resize_cover_center_png(img_bytes, target_w=target_w, target_h=target_h)
                mime = "image/png"
            except Exception:
                # resize 失败也尽量保存原图
                pass
        except Exception:
            # 文生图失败：本地兜底生成一张确定性图案
            img_bytes = _fallback_pattern_png(seed=title + "\n" + content, target_w=target_w, target_h=target_h)
            mime = "image/png"

        try:
            with open(abs_path, "wb") as f:
                f.write(img_bytes)

            rel_path = os.path.relpath(abs_path, PROJECT_ROOT)
            case["image_path"] = rel_path.replace(os.sep, "/")
        except Exception:
            continue


def build_db_aligned_payload(elite_ideas_content: str, max_tokens: int = 2048) -> dict:
    """
    将 Elite Ideas 文本转为与数据库字段对齐的结构。

    返回结构：
    {
      "elite_idea_cards": [...],
      "elite_idea_cases": [...],
      "external_resources": [...]
    }
    """
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": DB_JSON_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"请将以下 Elite Ideas 内容结构化为目标 JSON:\n\n{elite_ideas_content}",
                },
            ],
            temperature=0.2,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        parsed = json.loads(content)
        raw_cards = parsed.get("elite_idea_cards", []) if isinstance(parsed, dict) else []
        if not isinstance(raw_cards, list):
            raw_cards = []

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cards = []
        cases = []
        resources = []

        for idx, card in enumerate(raw_cards):
            if not isinstance(card, dict):
                continue

            cards.append(
                {
                    # 与 Learning_DB.elite_idea_cards 对齐
                    "daily_brief_id": None,
                    "origin_concept": _truncate(card.get("origin_concept", ""), 100),
                    "meta_idea_name": _truncate(card.get("meta_idea_name", ""), 100),
                    "meta_explanation": _truncate(card.get("meta_explanation", ""), 100),
                    "create_at": now_str,
                    # 非数据库字段：用于后续落库关联
                    "card_index": idx,
                }
            )

            raw_cases = card.get("cases", [])
            if isinstance(raw_cases, list):
                for c in raw_cases:
                    if not isinstance(c, dict):
                        continue
                    cases.append(
                        {
                            # 与 Learning_DB.elite_idea_cases 对齐
                            "meta_id": None,
                            "case_title": _truncate(c.get("case_title", ""), 100),
                            "case_content": _truncate(c.get("case_content", ""), 100),
                            "image_path": _truncate(c.get("image_path", ""), 100),
                            "query_rewrite": str(c.get("query_rewrite", "") or "").strip(),
                            # 非数据库字段：用于后续落库关联
                            "card_index": idx,
                        }
                    )

            raw_resources = card.get("external_resources", [])
            if isinstance(raw_resources, list):
                for r in raw_resources:
                    if not isinstance(r, dict):
                        continue
                    resources.append(
                        {
                            # 与 Learning_DB.external_resources 对齐
                            "card_id": None,
                            "title": _truncate(r.get("title", ""), 100),
                            "url": _truncate(r.get("url", ""), 100),
                            "LLM_context": str(r.get("LLM_context", "") or "").strip(),
                            "source": _truncate(r.get("source", ""), 100),
                            # 非数据库字段：用于后续落库关联
                            "card_index": idx,
                        }
                    )

        # 固定只保留 2 条卡片，并同步裁剪 cases/resources
        keep_indices = {0, 1}
        cards = [c for c in cards if c.get("card_index") in keep_indices][:2]
        cases = [c for c in cases if c.get("card_index") in keep_indices]
        resources = [r for r in resources if r.get("card_index") in keep_indices]

        return {
            "elite_idea_cards": cards,
            "elite_idea_cases": cases,
            "external_resources": resources,
        }

    except Exception as e:
        raise Exception(f"数据库对齐结构生成失败: {str(e)}")


def _resolve_handout_path(*, source_file: str | None = None, handout_filename: str | None = None) -> str:
    """定位讲义文件路径。

    - handout_filename: 例如 "upload_handout.json"（优先）
    - source_file: 例如 "upload.pdf"，将匹配 meta.source_file
    - 都不传：默认选择最新的一份 *_handout.json（按 mtime）
    """

    if handout_filename:
        fname = os.path.basename(handout_filename)
        path = handout_filename if os.path.isabs(handout_filename) else os.path.join(HANDOUT_DIR, fname)
        if not os.path.exists(path):
            raise FileNotFoundError(f"未找到讲义文件: {path}")
        return path

    if not os.path.isdir(HANDOUT_DIR):
        raise FileNotFoundError(f"讲义目录不存在: {HANDOUT_DIR}")

    if not source_file:
        candidates = [
            os.path.join(HANDOUT_DIR, fn)
            for fn in os.listdir(HANDOUT_DIR)
            if fn.endswith("_handout.json")
        ]
        if not candidates:
            raise FileNotFoundError(f"讲义目录为空: {HANDOUT_DIR}")
        return max(candidates, key=os.path.getmtime)

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

    return max(candidates, key=os.path.getmtime)


def _handout_to_text(handout: dict) -> str:
    """将讲义 JSON 归一化为可供 LLM 分析的纯文本。"""

    if not isinstance(handout, dict):
        return ""

    meta = handout.get("meta", {}) or {}
    title = str(meta.get("title", "") or "").strip()
    subject = str(meta.get("subject", "") or "").strip()
    source_file = str(meta.get("source_file", "") or "").strip()
    overview = str(handout.get("overview", "") or "").strip()
    summary = str(handout.get("summary", "") or "").strip()

    parts: list[str] = []
    if title or subject or source_file:
        parts.append(f"标题：{title}\n学科：{subject}\n来源：{source_file}".strip())
    if overview:
        parts.append(f"概述：\n{overview}")

    sections = handout.get("sections", [])
    if isinstance(sections, list):
        for i, sec in enumerate(sections, start=1):
            if not isinstance(sec, dict):
                continue
            sec_title = str(sec.get("title", "") or "").strip()
            sec_content = str(sec.get("content", "") or "").strip()
            if sec_title or sec_content:
                parts.append(f"第{i}部分：{sec_title}\n{sec_content}".strip())

            key_concepts = sec.get("key_concepts", [])
            if isinstance(key_concepts, list) and key_concepts:
                kc_lines: list[str] = []
                for kc in key_concepts:
                    if not isinstance(kc, dict):
                        continue
                    term = str(kc.get("term", "") or "").strip()
                    definition = str(kc.get("definition", "") or "").strip()
                    formula = str(kc.get("formula", "") or "").strip()
                    example = str(kc.get("example", "") or "").strip()
                    line = f"- {term}：{definition}"
                    if formula:
                        line += f"；公式：{formula}"
                    if example:
                        line += f"；例子：{example}"
                    kc_lines.append(line)
                if kc_lines:
                    parts.append("核心概念：\n" + "\n".join(kc_lines))

    if summary:
        parts.append(f"总结：\n{summary}")

    return "\n\n".join([p for p in parts if p.strip()])


def _base_name_from_handout_path(handout_path: str) -> str:
    stem = os.path.splitext(os.path.basename(handout_path))[0]
    if stem.endswith("_handout"):
        stem = stem[: -len("_handout")]
    return stem or "handout"


def _offline_db_payload_from_handout(handout: dict) -> dict:
    """离线兜底：不调用 LLM，从讲义结构里抽取 2 条卡片。

    目标：保证接口和落盘可用（不追求“最优洞见”）。
    """

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta = handout.get("meta", {}) or {}
    title = str(meta.get("title", "") or "").strip()

    candidates: list[dict] = []
    sections = handout.get("sections", [])
    if isinstance(sections, list):
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            sec_title = str(sec.get("title", "") or "").strip()
            sec_content = str(sec.get("content", "") or "").strip()
            key_concepts = sec.get("key_concepts", [])
            if isinstance(key_concepts, list) and key_concepts:
                for kc in key_concepts:
                    if not isinstance(kc, dict):
                        continue
                    term = str(kc.get("term", "") or "").strip()
                    definition = str(kc.get("definition", "") or "").strip()
                    if term:
                        candidates.append(
                            {
                                "origin_concept": sec_title or term,
                                "meta_idea_name": term,
                                "meta_explanation": definition or _truncate(sec_content, 100),
                            }
                        )
            elif sec_title or sec_content:
                candidates.append(
                    {
                        "origin_concept": sec_title,
                        "meta_idea_name": sec_title or title or "讲义核心洞见",
                        "meta_explanation": _truncate(sec_content, 100),
                    }
                )

    # 兜底：确保至少两条
    while len(candidates) < 2:
        candidates.append(
            {
                "origin_concept": title,
                "meta_idea_name": title or "讲义核心洞见",
                "meta_explanation": _truncate(str(handout.get("overview", "") or ""), 100),
            }
        )

    cards = []
    for idx, c in enumerate(candidates[:2]):
        cards.append(
            {
                "daily_brief_id": None,
                "origin_concept": _truncate(c.get("origin_concept", ""), 100),
                "meta_idea_name": _truncate(c.get("meta_idea_name", ""), 100),
                "meta_explanation": _truncate(c.get("meta_explanation", ""), 100),
                "create_at": now_str,
                "card_index": idx,
            }
        )

    return {
        "elite_idea_cards": cards,
        "elite_idea_cases": [],
        "external_resources": [],
    }


def process_handout_to_elite_ideas(
    *,
    source_file: str | None = None,
    handout_filename: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    save_to_file: bool = True,
    output_dir: str = ELITE_IDEAS_OUTPUT_DIR,
    force_regen: bool = False,
) -> dict:
    """从已落盘讲义中提取 Elite Ideas，并生成 DB 对齐结构。

    具备缓存机制：若已存在对应的 *_elite_ideas_db.json 且结构完整（>=2 cards），则直接复用。
    """

    start_time = time.time()

    handout_path = _resolve_handout_path(source_file=source_file, handout_filename=handout_filename)
    base_name = _base_name_from_handout_path(handout_path)

    output_json_path = os.path.join(output_dir, f"{base_name}_elite_ideas_db.json")
    output_md_path = os.path.join(output_dir, f"{base_name}_elite_ideas.md")

    if not force_regen and os.path.exists(output_json_path):
        try:
            # 讲义文件若比缓存更新，则必须重新生成（避免 handout 覆盖写同名文件时永远 cache_hit）
            if os.path.exists(handout_path):
                handout_mtime = os.path.getmtime(handout_path)
                cache_mtime = os.path.getmtime(output_json_path)
                if handout_mtime > cache_mtime:
                    raise RuntimeError("handout_newer_than_cache")

            with open(output_json_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            cards = cached.get("elite_idea_cards", []) if isinstance(cached, dict) else []
            cases = cached.get("elite_idea_cases", []) if isinstance(cached, dict) else []
            if isinstance(cards, list) and len([c for c in cards if isinstance(c, dict)]) >= 2:
                # 兼容：历史缓存可能不含 image_path；若启用文生图，则在 cache_hit 下补齐并回写。
                try:
                    if _should_generate_elite_ideas_images():
                        need_backfill_cards = False
                        for c in cards:
                            if not isinstance(c, dict):
                                continue
                            p = str(c.get("image_path", "") or "").strip()
                            if not p:
                                need_backfill_cards = True
                                break
                            abs_p = os.path.join(PROJECT_ROOT, p.replace("/", os.sep))
                            if not os.path.exists(abs_p):
                                need_backfill_cards = True
                                break

                        need_backfill_cases = False
                        if isinstance(cases, list) and cases:
                            for c in cases:
                                if not isinstance(c, dict):
                                    continue
                                p = str(c.get("image_path", "") or "").strip()
                                if not p:
                                    need_backfill_cases = True
                                    break
                                abs_p = os.path.join(PROJECT_ROOT, p.replace("/", os.sep))
                                if not os.path.exists(abs_p):
                                    need_backfill_cases = True
                                    break

                        if need_backfill_cards:
                            _maybe_generate_images_for_cards(base_name=base_name, cards=cards)
                        if need_backfill_cases:
                            _maybe_generate_images_for_cases(base_name=base_name, cases=cases)

                        if need_backfill_cards or need_backfill_cases:
                            with open(output_json_path, "w", encoding="utf-8") as wf:
                                json.dump(cached, wf, ensure_ascii=False, indent=2)
                except Exception:
                    pass

                # 兼容：历史缓存不含 search_and_generate 结果；在 cache_hit 下补齐并回写。
                try:
                    if str(os.getenv("ELITE_IDEAS_DISABLE_SG", "")).strip() != "1":
                        if isinstance(cases, list) and cases:
                            need_backfill_sg = False
                            for c in cases:
                                if not isinstance(c, dict):
                                    continue
                                sg = c.get("search_and_generate")
                                if not isinstance(sg, dict) or not sg:
                                    need_backfill_sg = True
                                    break

                            if need_backfill_sg:
                                try:
                                    from search_and_generate.main import main as sg_main
                                except Exception:
                                    sg_main = None

                                cards_by_index = {}
                                for card in cards:
                                    if not isinstance(card, dict):
                                        continue
                                    idx = card.get("card_index")
                                    if isinstance(idx, int):
                                        cards_by_index[idx] = card

                                if sg_main:
                                    memo = {}
                                    for c in cases:
                                        if not isinstance(c, dict):
                                            continue
                                        if isinstance(c.get("search_and_generate"), dict) and c.get("search_and_generate"):
                                            continue

                                        concept = str(c.get("query_rewrite", "") or "").strip()
                                        if not concept:
                                            concept = str(c.get("case_title", "") or "").strip()
                                        if not concept:
                                            ci = c.get("card_index")
                                            if isinstance(ci, int) and isinstance(cards_by_index.get(ci), dict):
                                                concept = str(cards_by_index[ci].get("meta_idea_name", "") or "").strip()
                                        concept = concept or ""

                                        if concept in memo:
                                            c["search_and_generate"] = memo[concept]
                                            continue

                                        try:
                                            # fetch_full=False: 避免抓取全文导致耗时/超大 JSON
                                            result = sg_main(concept, keywords=[concept], fetch_full=False)
                                            if not isinstance(result, dict):
                                                result = {"error": "search_and_generate returned non-dict"}
                                        except Exception as e:
                                            result = {"error": str(e)}

                                        memo[concept] = result
                                        c["search_and_generate"] = result

                                    with open(output_json_path, "w", encoding="utf-8") as wf:
                                        json.dump(cached, wf, ensure_ascii=False, indent=2)
                except Exception:
                    pass

                return {
                    "success": True,
                    "stage": "cache_hit",
                    "handout_path": handout_path,
                    "output_json_path": output_json_path,
                    "output_path": output_md_path if os.path.exists(output_md_path) else None,
                    "db_aligned_payload": cached,
                    "db_payload_error": None,
                    "elapsed_time": round(time.time() - start_time, 2),
                }
        except Exception:
            # 缓存损坏则继续走生成
            pass

    # 读取讲义
    with open(handout_path, "r", encoding="utf-8") as f:
        handout = json.load(f)
    if not isinstance(handout, dict):
        return {
            "success": False,
            "error": "讲义内容不是合法 JSON 对象",
            "stage": "handout_load",
            "handout_path": handout_path,
        }

    handout_text = _handout_to_text(handout)
    if not handout_text.strip():
        return {
            "success": False,
            "error": "讲义文本为空，无法提取 Elite Ideas",
            "stage": "handout_text",
        }

    disable_llm = str(os.getenv("ELITE_IDEAS_DISABLE_LLM", "")).strip() == "1"

    elite_ideas_content = ""
    db_aligned_payload = {
        "elite_idea_cards": [],
        "elite_idea_cases": [],
        "external_resources": [],
    }
    db_payload_error = None

    if disable_llm:
        # 离线兜底：直接从讲义结构抽取两条
        db_aligned_payload = _offline_db_payload_from_handout(handout)
        cards = db_aligned_payload.get("elite_idea_cards", [])
        if isinstance(cards, list):
            elite_ideas_content = "\n\n".join(
                [
                    f"【标题】{c.get('meta_idea_name','')}\n【讲义来源】{c.get('origin_concept','')}\n【洞见阐释】{c.get('meta_explanation','')}"
                    for c in cards
                    if isinstance(c, dict)
                ]
            )
    else:
        # 提取 Elite Ideas（固定 2 条由 system prompt 约束）
        try:
            elite_ideas_content = extract_elite_ideas(handout_text, max_tokens=max_tokens, temperature=temperature)
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "stage": "elite_ideas_extraction",
                "handout_path": handout_path,
                "output_json_path": output_json_path,
                "output_path": output_md_path,
            }

        # 生成数据库对齐结构（失败不影响主流程）
        try:
            db_aligned_payload = build_db_aligned_payload(elite_ideas_content)
        except Exception as e:
            db_payload_error = str(e)

    if save_to_file:
        # 文生图：为 2 条 Elite Ideas 生成配图（失败不阻断）
        try:
            cards = db_aligned_payload.get("elite_idea_cards", []) if isinstance(db_aligned_payload, dict) else []
            if isinstance(cards, list) and cards:
                _maybe_generate_images_for_cards(base_name=base_name, cards=cards)
        except Exception:
            pass

        # 文生图：为每条 case 生成配图（失败不阻断）
        try:
            cases = db_aligned_payload.get("elite_idea_cases", []) if isinstance(db_aligned_payload, dict) else []
            if isinstance(cases, list) and cases:
                _maybe_generate_images_for_cases(base_name=base_name, cases=cases)
        except Exception:
            pass

        # search_and_generate：为每条 case 生成扩写/压缩等结果（失败不阻断）
        try:
            if str(os.getenv("ELITE_IDEAS_DISABLE_SG", "")).strip() != "1":
                try:
                    from search_and_generate.main import main as sg_main
                except Exception:
                    sg_main = None

                if sg_main and isinstance(db_aligned_payload, dict):
                    cards = db_aligned_payload.get("elite_idea_cards", [])
                    cases = db_aligned_payload.get("elite_idea_cases", [])
                    cards_by_index = {}
                    if isinstance(cards, list):
                        for card in cards:
                            if not isinstance(card, dict):
                                continue
                            idx = card.get("card_index")
                            if isinstance(idx, int):
                                cards_by_index[idx] = card

                    if isinstance(cases, list) and cases:
                        memo = {}
                        for c in cases:
                            if not isinstance(c, dict):
                                continue

                            if isinstance(c.get("search_and_generate"), dict) and c.get("search_and_generate"):
                                continue

                            concept = str(c.get("query_rewrite", "") or "").strip()
                            if not concept:
                                concept = str(c.get("case_title", "") or "").strip()
                            if not concept:
                                ci = c.get("card_index")
                                if isinstance(ci, int) and isinstance(cards_by_index.get(ci), dict):
                                    concept = str(cards_by_index[ci].get("meta_idea_name", "") or "").strip()
                            concept = concept or ""

                            if concept in memo:
                                c["search_and_generate"] = memo[concept]
                                continue

                            try:
                                result = sg_main(concept, keywords=[concept], fetch_full=False)
                                if not isinstance(result, dict):
                                    result = {"error": "search_and_generate returned non-dict"}
                            except Exception as e:
                                result = {"error": str(e)}

                            memo[concept] = result
                            c["search_and_generate"] = result
        except Exception:
            pass

        os.makedirs(output_dir, exist_ok=True)
        try:
            with open(output_md_path, "w", encoding="utf-8") as f:
                f.write(f"# {base_name} - Elite Ideas 挖掘\n\n")
                f.write(f"**生成时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(elite_ideas_content)
        except Exception:
            output_md_path = None

        try:
            with open(output_json_path, "w", encoding="utf-8") as f:
                json.dump(db_aligned_payload, f, ensure_ascii=False, indent=2)
        except Exception:
            output_json_path = None

        # 对于存储模式：JSON 是主产物，写失败应视为失败
        if not output_json_path:
            return {
                "success": False,
                "error": "Elite Ideas JSON 落盘失败（请检查运行目录权限/磁盘空间）",
                "stage": "persist_failed",
                "handout_path": handout_path,
                "output_json_path": None,
                "output_path": output_md_path,
                "elapsed_time": round(time.time() - start_time, 2),
            }

    return {
        "success": True,
        "stage": "generated",
        "handout_path": handout_path,
        "elite_ideas": elite_ideas_content,
        "db_aligned_payload": db_aligned_payload,
        "db_payload_error": db_payload_error,
        "output_path": output_md_path,
        "output_json_path": output_json_path,
        "elapsed_time": round(time.time() - start_time, 2),
    }


def process_pdf_to_elite_ideas(
    pdf_path: str, 
    filename: str = None,
    max_pages: int = None,
    save_to_file: bool = False,
    output_dir: str = ELITE_IDEAS_OUTPUT_DIR
) -> dict:
    """
    从 PDF 文件中提取并分析 Elite Ideas
    
    Args:
        pdf_path: PDF 文件路径
        filename: 文件名（用于输出）
        max_pages: 最大提取页数
        save_to_file: 是否保存到文件
        output_dir: 输出目录
        
    Returns:
        包含提取结果的字典
    """
    start_time = time.time()
    
    # 提取文本
    try:
        full_text = extract_pdf_text(pdf_path, max_pages)
        text_length = len(full_text)
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "stage": "text_extraction"
        }
    
    # 提取 Elite Ideas
    try:
        elite_ideas_content = extract_elite_ideas(full_text)
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "stage": "elite_ideas_extraction",
            "text_length": text_length
        }
    
    # 生成数据库对齐结构（失败不影响主流程）
    db_aligned_payload = {
        "elite_idea_cards": [],
        "elite_idea_cases": [],
        "external_resources": [],
    }
    db_payload_error = None
    try:
        db_aligned_payload = build_db_aligned_payload(elite_ideas_content)
    except Exception as e:
        db_payload_error = str(e)

    # 可选：保存到文件
    output_path = None
    output_json_path = None
    if save_to_file:
        try:
            os.makedirs(output_dir, exist_ok=True)
            base_name = filename or os.path.basename(pdf_path)
            base_name = os.path.splitext(base_name)[0]
            output_filename = f"{base_name}_elite_ideas.md"
            output_path = os.path.join(output_dir, output_filename)
            
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(f"# {base_name} - Elite Ideas 挖掘\n\n")
                f.write(f"**生成时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(elite_ideas_content)

            # 同步保存数据库对齐 JSON，便于后续直接入库
            output_json_filename = f"{base_name}_elite_ideas_db.json"
            output_json_path = os.path.join(output_dir, output_json_filename)
            with open(output_json_path, "w", encoding="utf-8") as f:
                json.dump(db_aligned_payload, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            # 文件保存失败不影响返回结果
            output_path = f"保存失败: {str(e)}"
    
    # 计算耗时
    elapsed_time = time.time() - start_time
    
    return {
        "success": True,
        "filename": filename or os.path.basename(pdf_path),
        "text_length": text_length,
        "elite_ideas": elite_ideas_content,
        "db_aligned_payload": db_aligned_payload,
        "db_payload_error": db_payload_error,
        "output_path": output_path,
        "output_json_path": output_json_path,
        "elapsed_time": round(elapsed_time, 2)
    }
