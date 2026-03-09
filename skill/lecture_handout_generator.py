import os
import time
import json
import fitz
import threading
from datetime import datetime, timezone
from openai import OpenAI
from .config import ZHIZENGZENG_API_KEY, ZHIZENGZENG_BASE_URL, MODEL_NAME, OUTPUT_DIR

# 初始化客户端
client = OpenAI(api_key=ZHIZENGZENG_API_KEY, base_url=ZHIZENGZENG_BASE_URL)

# 讲义存储目录
HANDOUT_DIR = os.path.join(os.path.dirname(OUTPUT_DIR), "handouts")
os.makedirs(HANDOUT_DIR, exist_ok=True)


def extract_text_with_structure(pdf_path, max_pages=30):
    """提取 PDF 文本，尽量保留段落结构"""
    try:
        doc = fitz.open(pdf_path)
        pages_text = []
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            text = page.get_text("text")
            if text.strip():
                pages_text.append(f"[第 {i + 1} 页]\n{text}")
        return "\n\n".join(pages_text)
    except Exception as e:
        print(f"PDF 提取错误: {e}")
        return None


def generate_handout_json(text, filename=""):
    """
    调用 LLM 将 PDF 文本生成结构化讲义 JSON

    讲义结构：
    {
        "meta": {
            "title": "讲义标题",
            "subject": "学科/课程名",
            "source_file": "xxx.pdf",
            "generated_at": "2026-03-03"
        },
        "overview": "课程/章节整体概述（2-4句话）",
        "sections": [
            {
                "title": "章节标题",
                "content": "该节的核心知识点叙述",
                "key_concepts": [
                    {
                        "term": "概念术语",
                        "definition": "定义解释",
                        "formula": "相关公式或表达式（无则为空字符串）",
                        "example": "具体示例（无则为空字符串）"
                    }
                ],
                "notes": "补充说明或学习要点"
            }
        ],
        "summary": "全文总结（3-5句话）",
        "review_questions": [
            "复习思考题1",
            "复习思考题2",
            "复习思考题3"
        ]
    }
    """
    system_prompt = """
你是一位资深高校教师，擅长将学术材料整理成清晰、系统的讲义。

请将用户提供的文本内容整理为一份结构完整的中文教学讲义（即使原文是英文，也必须全部翻译为中文输出）。

输出必须是以下结构的 JSON，不要包含任何 Markdown 代码块：

{
    "meta": {
        "title": "讲义标题（从内容中提取）",
        "subject": "所属学科/课程名称",
        "source_file": "{{filename}}",
        "generated_at": "{{date}}"
    },
    "overview": "简短概述本讲义涵盖的核心主题，2~4句话",
    "sections": [
        {
            "title": "章节/知识点标题",
            "content": "该部分核心知识的详细叙述，150字以上，需要完整解释原理、逻辑或推导过程",
            "key_concepts": [
                {
                    "term": "概念名称",
                    "definition": "清晰的定义",
                    "formula": "数学公式或表达式，无则为空字符串",
                    "example": "具体示例或应用场景，无则为空字符串"
                }
            ],
            "notes": "学习提示或重难点提醒，可为空字符串"
        }
    ],
    "summary": "对整份讲义的总结性段落，3~5句话",
    "review_questions": [
        "思考题或例题，至少3道"
    ]
}

要求：
1. sections 数量根据内容自然划分，至少 3 个，最多 10 个
2. 每个 section 的 key_concepts 至少 1 个，重要节可有 3~5 个
3. 公式务必准确，使用 LaTeX 风格（如 H(X) = -\\sum p(x) \\log p(x)）
4. 只返回纯 JSON，绝对不要 Markdown 代码块
"""

    system_prompt = system_prompt.replace("{{filename}}", filename).replace(
        "{{date}}", time.strftime("%Y-%m-%d")
    )

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请根据以下文本生成讲义：\n\n{text[:40000]}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"LLM 调用错误: {e}")
        return None


def save_handout_local(filename, json_data):
    """将讲义 JSON 保存到本地"""
    base_name = os.path.splitext(filename)[0]
    json_path = os.path.join(HANDOUT_DIR, f"{base_name}_handout.json")

    with open(json_path, "w", encoding="utf-8") as f:
        f.write(json_data)

    print(f"💾 讲义已保存: {json_path}")
    return json_path


def handout_to_markdown(handout_dict):
    """
    将讲义 JSON 转换为 Markdown 格式，便于阅读或前端渲染
    返回 Markdown 字符串
    """
    lines = []
    meta = handout_dict.get("meta", {})

    lines.append(f"# {meta.get('title', '讲义')}")
    lines.append(f"> **学科**：{meta.get('subject', '')}　　**来源文件**：{meta.get('source_file', '')}　　**生成日期**：{meta.get('generated_at', '')}")
    lines.append("")

    lines.append("## 概述")
    lines.append(handout_dict.get("overview", ""))
    lines.append("")

    for idx, section in enumerate(handout_dict.get("sections", []), 1):
        lines.append(f"## {idx}. {section.get('title', '')}")
        lines.append("")
        lines.append(section.get("content", ""))
        lines.append("")

        key_concepts = section.get("key_concepts", [])
        if key_concepts:
            lines.append("### 核心概念")
            for concept in key_concepts:
                lines.append(f"**{concept.get('term', '')}**")
                lines.append(f"- 定义：{concept.get('definition', '')}")
                if concept.get("formula"):
                    lines.append(f"- 公式：$${concept['formula']}$$")
                if concept.get("example"):
                    lines.append(f"- 示例：{concept['example']}")
                lines.append("")

        notes = section.get("notes", "")
        if notes:
            lines.append(f"> 📌 **学习提示**：{notes}")
            lines.append("")

    lines.append("## 总结")
    lines.append(handout_dict.get("summary", ""))
    lines.append("")

    review_questions = handout_dict.get("review_questions", [])
    if review_questions:
        lines.append("## 复习思考题")
        for i, q in enumerate(review_questions, 1):
            lines.append(f"{i}. {q}")
        lines.append("")

    return "\n".join(lines)


def process_pdf_to_handout(pdf_path, filename=None, max_pages=30):
    """
    处理 PDF 并生成讲义的主函数

    Returns:
        dict: {
            "status": "success",
            "process_time": "x.xxs",
            "file_name": "xxx.pdf",
            "archived_at": "/path/to/handout.json",
            "data": { ...讲义 JSON... },
            "markdown": "...Markdown 格式的讲义..."
        }
    """
    start_time = time.time()
    fname = filename or os.path.basename(pdf_path)

    # 1. 提取 PDF 文本
    raw_text = extract_text_with_structure(pdf_path, max_pages=max_pages)
    if not raw_text:
        raise RuntimeError("无法从 PDF 中提取文字")

    # 2. LLM 生成讲义 JSON
    json_str = generate_handout_json(raw_text, filename=fname)
    if not json_str:
        raise RuntimeError("AI 服务响应失败")

    # 3. 解析 JSON，并注入 created_at
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        parsed = json.loads(json_str)
        parsed["created_at"] = created_at          # 写入 JSON 数据
        json_str = json.dumps(parsed, ensure_ascii=False, indent=2)
    except Exception:
        parsed = {"raw_output": json_str, "error": "JSON 解析失败", "created_at": created_at}

    # 4. 保存到本地（含 created_at）
    archived_path = save_handout_local(fname, json_str)

    # 5. 生成 Markdown 版本
    markdown_content = ""
    if isinstance(parsed, dict) and "sections" in parsed:
        try:
            markdown_content = handout_to_markdown(parsed)
            # 同时保存 Markdown 文件
            md_path = archived_path.replace("_handout.json", "_handout.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            print(f"📄 Markdown 讲义已保存: {md_path}")
        except Exception as e:
            print(f"⚠️ Markdown 转换失败: {e}")

    return {
        "status": "success",
        "process_time": f"{time.time() - start_time:.2f}s",
        "file_name": fname,
        "archived_at": archived_path,
        "created_at": created_at,
        "data": parsed,
        "markdown": markdown_content,
    }
