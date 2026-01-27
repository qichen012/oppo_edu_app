"""
查询重写模块
使用 DeepSeek API 对用户查询进行语义重写，融合对话历史信息
"""

from openai import OpenAI
from typing import List, Dict
from skill.config import DEEPSEEK_BASE_URL, DEEPSEEK_API_KEY, DEEPSEEK_MODEL


# 初始化 DeepSeek 客户端
client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL
)


def semantic_rewrite(history: List[Dict[str, str]], current_query: str) -> str:
    """
    使用 DeepSeek 对 query 进行语义重写
    
    Args:
        history: 历史对话列表 [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
        current_query: 用户当前的输入
        
    Returns:
        重写后的 Query
    """
    
    # 构造 System Prompt，包含查询重写策略
    system_prompt = """
你是一个查询重写（Query Rewriting）专家。请根据以下对话历史，将用户的"当前输入"重写为一个适合搜索引擎检索的、独立完整的陈述句。

示例 1 (上下文融合):
历史: User: "华为 Mate 60 多少钱？" Assistant: "6999元起。"
当前输入: "Pro 版呢？"
重写结果: 华为 Mate 60 Pro 的价格是多少？

示例 2 (消除歧义):
历史: User: "我想了解 iPhone 15 Pro。"
当前输入: "它怎么截屏？"
重写结果: iPhone 15 Pro 如何截屏？

请严格只输出重写后的句子，不要包含任何解释。
"""

    # 将历史记录格式化为文本块
    history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])
    
    user_prompt = f"""
【对话历史】
{history_text}

【当前输入】
{current_query}

【重写结果】
"""

    try:
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,  # 重写任务需要低随机性，确保稳定
            max_tokens=100    # 输出通常很短
        )
        
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        # 如果重写失败，返回原始查询
        print(f"查询重写失败: {e}")
        return current_query
