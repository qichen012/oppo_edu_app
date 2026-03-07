"""
Elite Ideas 提取器
从 PDF 讲义中提取有价值的 Meta Ideas 和 Elite Ideas
"""
import os
import time
import json
import fitz  # PyMuPDF
from openai import OpenAI
from .config import ZHIZENGZENG_API_KEY, ZHIZENGZENG_BASE_URL, MODEL_NAME


# 初始化客户端
client = OpenAI(api_key=ZHIZENGZENG_API_KEY, base_url=ZHIZENGZENG_BASE_URL)


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
- 共输出 8～15 条 Elite Ideas，按重要性或启发性排序
- 语言：中文，风格：深刻但不晦涩

【重要提示】
请基于讲义实际内容进行分析，不要泛泛而谈。每条洞见都必须有清晰的讲义知识点作为根基。"""


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


def process_pdf_to_elite_ideas(
    pdf_path: str, 
    filename: str = None,
    max_pages: int = None,
    save_to_file: bool = False,
    output_dir: str = "data/processed_notes"
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
    
    # 可选：保存到文件
    output_path = None
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
        "output_path": output_path,
        "elapsed_time": round(elapsed_time, 2)
    }
