"""
knowledge_tree_generator.py
从 PDF 文件生成结构化"知识树" JSON。

核心流程：
  1. 用 PyMuPDF 提取文本 + 启发式识别章节标题
  2. 调用 LLM 生成章节骨架（outline）
  3. 调用 LLM 补充每节细节 + 挖掘跨章节非线性关联 (relatedNodeId)
  4. 校验并返回符合前端 TreeRoot 格式的 dict

对外暴露的入口：
  process_pdf_to_knowledge_tree(file_path, filename=None) -> dict   # 从文件路径读取
  process_bytes_to_knowledge_tree(pdf_bytes, filename="")  -> dict  # 直接传入字节（供异步 job 使用）
"""

import os
import re
import json
import time
import fitz  # PyMuPDF
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI
from pydantic import BaseModel, Field

from .config import ZHIZENGZENG_API_KEY, ZHIZENGZENG_BASE_URL, MODEL_NAME

# -------------------------
# OpenAI 客户端
# -------------------------
client = OpenAI(api_key=ZHIZENGZENG_API_KEY, base_url=ZHIZENGZENG_BASE_URL)

# -------------------------
# Pydantic 数据模型（用于校验）
# -------------------------
class Node(BaseModel):
    id: str
    title: str
    content: str
    relatedNodeId: Optional[str] = None
    children: List["Node"] = Field(default_factory=list)

Node.model_rebuild()

class TreeRoot(BaseModel):
    id: str
    title: str
    content: str
    children: List[Node] = Field(default_factory=list)


# =========================================================
# 公开入口
# =========================================================
def process_bytes_to_knowledge_tree(pdf_bytes: bytes, filename: str = "") -> Dict[str, Any]:
    """
    直接接收 PDF 字节数据，生成知识树 JSON 并返回。
    供异步 job（BackgroundTasks）场景使用，避免重复读文件。
    """
    start = time.time()

    if not pdf_bytes:
        raise ValueError("PDF 文件为空")

    text, headings = _extract_pdf_text_and_headings(pdf_bytes)
    if len(text.strip()) < 50:
        raise ValueError("PDF 文本提取内容过短，可能是扫描件（无 OCR 层）")

    outline = _llm_build_outline(text, headings)
    enriched = _llm_enrich_tree(text, outline)
    tree = TreeRoot.model_validate(enriched).model_dump()

    return {
        "success": True,
        "filename": filename,
        "tree": tree,
        "processing_time": round(time.time() - start, 2),
    }


def process_pdf_to_knowledge_tree(file_path: str, filename: str = None) -> Dict[str, Any]:
    """
    读取本地 PDF 文件，生成知识树 JSON 并返回。
    """
    filename = filename or os.path.basename(file_path)
    with open(file_path, "rb") as f:
        pdf_bytes = f.read()
    return process_bytes_to_knowledge_tree(pdf_bytes, filename=filename)


# =========================================================
# PDF 文本提取
# =========================================================
def _extract_pdf_text_and_headings(pdf_bytes: bytes) -> Tuple[str, List[str]]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    parts: List[str] = []
    headings: List[str] = []

    for i, page in enumerate(doc):
        t = page.get_text("text") or ""
        parts.append(f"\n\n--- PAGE {i+1} ---\n{t}")

        # 启发式：识别带编号的短标题行（如 "1.2 梯度下降"）
        for line in t.splitlines():
            line_s = line.strip()
            if 0 < len(line_s) <= 60 and re.match(r"^(\d+(\.\d+)*)\s+.+", line_s):
                headings.append(line_s)

    full_text = "\n".join(parts)

    # 去重并截取前 60 条
    seen: set = set()
    uniq: List[str] = []
    for h in headings:
        if h not in seen:
            uniq.append(h)
            seen.add(h)
    return full_text, uniq[:60]


# =========================================================
# LLM 调用
# =========================================================
def _llm_build_outline(full_text: str, headings: List[str]) -> Dict[str, Any]:
    """第一步：生成章节骨架（content 可以很短）"""
    clipped = _clip_text(full_text, 120_000)
    headings_text = "\n".join(headings[:60])

    system = (
        "你是一个专业的文档结构化分析助手。"
        "任务：先生成章节/子章节/关键知识点的层级结构（树），不要展开太多细节。"
        "必须只输出严格JSON，不能输出任何解释性文字。"
    )
    user = f"""
请基于文档内容与可能的章节标题，生成"知识树骨架JSON"。

输出必须符合以下格式：
{{
  "id": "root_01",
  "title": "文档标题或主题",
  "content": "一句话概述（很短）",
  "children": [
    {{
      "id": "ch01",
      "title": "章节名称",
      "content": "章节一句话概述（很短）",
      "relatedNodeId": null,
      "children": [
        {{
          "id": "ch01_kp01",
          "title": "子知识点标题",
          "content": "（先留空或一句话）",
          "relatedNodeId": null,
          "children": []
        }}
      ]
    }}
  ]
}}

约束：
1) id 全局唯一、可引用，建议 ch01/ch02...；子节点 ch01_kp01/ch01_kp02...
2) children 至少包含 4-8 个一级章节（若文档确实较短可少一些，但尽量覆盖）
3) 此步骤只做结构，不要写长内容，不要公式推导。
4) 不必只做成两层，可以有三/四级（章节-小节-知识点），但不要过深。

可能的章节标题（如果有）：
{headings_text}

文档内容（截断）：
{clipped}
"""
    raw = _llm_json_call(system, user, temperature=0.2)
    obj = _parse_json(raw)
    return _normalize_tree(obj, skeleton_ok=True)


def _llm_enrich_tree(full_text: str, outline: Dict[str, Any]) -> Dict[str, Any]:
    """第二步：补充每节细节、公式、变量说明、非线性关联"""
    clipped = _clip_text(full_text, 160_000)

    system = (
        "你是一个专业的文档分析助手。"
        "目标：在给定的知识树骨架上，补充每个节点的详细内容，尤其是数学公式、定义、变量解释与适用条件。"
        "此外，重点挖掘知识点之间的非线性关联结构，使用 relatedNodeId 指向另一个节点 id。"
        "必须只输出严格JSON，不能输出任何解释性文字。"
    )
    user = f"""
下面给出"知识树骨架JSON"（content 很短或为空）。请你在保持结构基本稳定的前提下：
1) 为每个节点补充 content（可使用 LaTeX 书写公式；给出变量含义与条件）。
2) 至少添加 8 条跨章节/跨子树的 relatedNodeId（非线性关联），且 relatedNodeId 必须指向树内真实存在的 id。
3) 禁止输出大而空的概述，重点写"可用于知识卡片"的细节。
4) 输出必须是严格 JSON。

骨架JSON：
{json.dumps(outline, ensure_ascii=False)}

文档内容（截断）：
{clipped}
"""
    raw = _llm_json_call(system, user, temperature=0.2)
    obj = _parse_json(raw)

    try:
        obj = _normalize_tree(obj, skeleton_ok=False)
        TreeRoot.model_validate(obj)
        return obj
    except Exception:
        # 一次自动修复机会
        repaired = _llm_repair_json(obj)
        repaired = _normalize_tree(repaired, skeleton_ok=False)
        TreeRoot.model_validate(repaired)
        return repaired


def _llm_repair_json(bad_obj: Any) -> Dict[str, Any]:
    system = (
        "你是一个JSON修复器。"
        "输入可能是格式不规范或字段缺失的对象。"
        "你必须输出严格JSON，修复为符合知识树格式：root + children，"
        "每个节点含 id/title/content/relatedNodeId/children。"
        "relatedNodeId 必须是 null 或树内真实存在的 id。"
        "不要输出任何解释。"
    )
    user = f"""
请修复并规范化为知识树JSON，输入如下（可能不完整）：
{json.dumps(bad_obj, ensure_ascii=False)}
"""
    raw = _llm_json_call(system, user, temperature=0.0)
    return _parse_json(raw)


def _llm_json_call(system: str, user: str, temperature: float = 0.2) -> str:
    resp = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


# =========================================================
# 工具函数
# =========================================================
def _clip_text(s: str, max_chars: int) -> str:
    s = s or ""
    return s if len(s) <= max_chars else s[:max_chars] + "\n[...TRUNCATED...]"


def _parse_json(raw: str) -> Dict[str, Any]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = raw.replace("```", "").strip()
    try:
        return json.loads(raw)
    except Exception:
        m1, m2 = raw.find("{"), raw.rfind("}")
        if m1 >= 0 and m2 > m1:
            return json.loads(raw[m1: m2 + 1])
        raise ValueError(f"无法解析 LLM 返回的 JSON，原始内容前200字：{raw[:200]}")


def _normalize_tree(obj: Any, skeleton_ok: bool) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError("知识树必须是一个 JSON 对象")

    def norm_node(n: Any) -> Dict[str, Any]:
        if not isinstance(n, dict):
            raise ValueError("节点必须是对象")
        nid = str(n.get("id", "")).strip()
        title = str(n.get("title", "")).strip()
        content = str(n.get("content", "")).strip()
        if not nid or not title:
            raise ValueError("节点缺少 id 或 title 字段")
        if not skeleton_ok and len(content) < 2:
            content = "（待补充）"
        rel = n.get("relatedNodeId", None)
        if rel is not None:
            rel = None if (rel == "" or str(rel).lower() == "null") else str(rel)
        children = n.get("children") or []
        if not isinstance(children, list):
            children = []
        return {
            "id": nid,
            "title": title,
            "content": content,
            "relatedNodeId": rel,
            "children": [norm_node(ch) for ch in children],
        }

    root_norm = {
        "id": str(obj.get("id", "root_01")).strip() or "root_01",
        "title": str(obj.get("title", "文档")).strip() or "文档",
        "content": str(obj.get("content", "概述")).strip() or "概述",
        "children": [norm_node(ch) for ch in (obj.get("children") or []) if isinstance(ch, dict)],
    }

    # 最终阶段：修正非法的 relatedNodeId 引用
    if not skeleton_ok:
        valid_ids: set = set()
        _collect_ids(root_norm, valid_ids)
        _fix_related_ids(root_norm, valid_ids)

    return root_norm


def _collect_ids(node: Dict[str, Any], out: set):
    out.add(node["id"])
    for ch in node.get("children", []):
        _collect_ids(ch, out)


def _fix_related_ids(node: Dict[str, Any], valid_ids: set):
    rel = node.get("relatedNodeId")
    if rel is not None and rel not in valid_ids:
        node["relatedNodeId"] = None
    for ch in node.get("children", []):
        _fix_related_ids(ch, valid_ids)
