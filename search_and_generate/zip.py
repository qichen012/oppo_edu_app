import os
from openai import OpenAI
try:
    from .api import get_qwen_client
except ImportError:  # 兼容：直接运行脚本
    from api import get_qwen_client


def _to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                title = str(item.get("title", "") or "").strip()
                url = str(item.get("url", "") or "").strip()
                content = str(item.get("content", "") or "").strip()
                parts.append(f"标题：{title}\n链接：{url}\n内容：{content}".strip())
            else:
                parts.append(str(item))
        return "\n\n".join(parts)
    if isinstance(value, dict):
        return "\n".join(f"{k}: {v}" for k, v in value.items())
    return str(value)


def zip_content(text):
    """
    压缩函数：使用Qwen模型将搜索到的的内容简要呈现为一段话
    
    参数:
        text: str - 要压缩的文本
    
    返回:
        str - 简要压缩后的一段话
    """
    raw_text = _to_text(text)
    if not raw_text.strip():
        return "无内容可供压缩"
    
    print("📦 [压缩] 正在使用Qwen精简内容...")
    
    client = get_qwen_client()
    
    prompt = f"""请将以下内容精简按照核心要点总结为几段话：

{raw_text}

要求：
1. 只输出几段话，每段话不超过300字，按要点进行分段落，每个段落包含一个要点。
2. 每个段落的要点作为小标题单独列出。
3. 包含概念名称和主要现实联系
4. 语言简洁明了

直接输出精简后的几段话："""

    try:
        if client:
            resp = client.chat.completions.create(
                model="qwen-plus",
                messages=[
                    {"role": "system", "content": "你是一个文字精简助手，擅长将内容压缩为简洁的摘要。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            result = resp.choices[0].message.content.strip()
            print("✅ 压缩完成")
            return result
        else:
            return "⚠️ 未找到Qwen API Key（DASHSCOPE_API_KEY），无法压缩。"
            
    except Exception as e:
        return f"❌ Qwen调用失败: {e}"