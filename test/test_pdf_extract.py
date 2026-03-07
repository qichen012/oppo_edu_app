import sys
import os

# 将项目根目录加入路径，以便导入 skill/config.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import fitz  # PyMuPDF
from openai import OpenAI
from skill.config import ZHIZENGZENG_BASE_URL, ZHIZENGZENG_API_KEY, MODEL_NAME

# ── 1. 提取 PDF 文本 ──────────────────────────────────────────
pdf_path = "./data/test/test_of_note.pdf"

doc = fitz.open(pdf_path)
print(f"共 {len(doc)} 页，正在提取文本…\n{'='*60}")

all_text_parts = []
for i, page in enumerate(doc):
    text = page.get_text().strip()
    if text:
        all_text_parts.append(f"【第 {i+1} 页】\n{text}")

doc.close()

full_text = "\n\n".join(all_text_parts)
print(f"文本提取完毕，共 {len(full_text)} 字符。\n")

# ── 2. 构建 Prompt ────────────────────────────────────────────
SYSTEM_PROMPT = """你是一位见识卓越的学者与思想家，精通从各类学科知识中提炼底层智慧。
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
- 共输出 8～15 条 Elite Ideas，按重要性或启发性排序
- 语言：中文，风格：深刻但不晦涩

【重要提示】
请基于讲义实际内容进行分析，不要泛泛而谈。每条洞见都必须有清晰的讲义知识点作为根基。"""

USER_PROMPT = f"""以下是我的课程讲义全文，请帮我挖掘其中有价值的 Elite Ideas：

{full_text}

请按照要求格式输出分析结果。"""

# ── 3. 调用大模型 ─────────────────────────────────────────────
client = OpenAI(
    base_url=ZHIZENGZENG_BASE_URL,
    api_key=ZHIZENGZENG_API_KEY,
)

print("正在调用大模型分析讲义，请稍候…\n" + "="*60)

response = client.chat.completions.create(
    model=MODEL_NAME,
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": USER_PROMPT},
    ],
    temperature=0.7,
    max_tokens=4096,
)

result = response.choices[0].message.content

print("\n" + "="*60)
print("【信息论讲义 Elite Ideas 挖掘结果】")
print("="*60)
print(result)

# ── 4. 可选：保存结果到文件 ────────────────────────────────────
output_path = "./data/test/elite_ideas_output.md"
with open(output_path, "w", encoding="utf-8") as f:
    f.write("# 讲义 Elite Ideas 挖掘\n\n")
    f.write(result)

print(f"\n结果已保存至：{output_path}")
