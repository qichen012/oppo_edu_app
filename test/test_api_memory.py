from openai import OpenAI
import os

# 初始化 DeepSeek 客户端
client = OpenAI(
    api_key="sk-d2c5fcabbec64ea19790f9c62d09473d",  # 替换为你的 API Key
    base_url="https://api.deepseek.com"
)

def semantic_rewrite(history, current_query):
    """
    使用 DeepSeek 对 query 进行语义重写
    :param history: 历史对话列表 [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    :param current_query: 用户当前的输入
    :return: 重写后的 Query
    """
    
    # 构造 System Prompt，包含你要求的 A/B 两类策略
    system_prompt = """
    你是一个查询重写（Query Rewriting）专家。请根据以下对话历史，将用户的“当前输入”重写为一个适合搜索引擎检索的、独立完整的陈述句。
    
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

    # 构造发送给 LLM 的消息体
    # 我们把历史记录转化成文本摘要放入 Prompt，或者直接作为 context 传入（视 token 长度而定）
    # 这里为了精准控制，我们将历史记录格式化为文本块传给 LLM
    
    history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])
    
    user_prompt = f"""
    【对话历史】
    {history_text}
    
    【当前输入】
    {current_query}
    
    【重写结果】
    """

    response = client.chat.completions.create(
        model="deepseek-chat",  # 使用 DeepSeek-V3
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.1,  # 重写任务需要低随机性，确保稳定
        max_tokens=100    # 输出通常很短
    )

    return response.choices[0].message.content.strip()

# ================= 模拟测试 =================

# 场景：上下文融合
chat_history = [
    {"role": "user", "content": "帮我查一下北京邮电大学的信息工程专业。"},
    {"role": "assistant", "content": "好的，这是关于北邮信息工程专业的相关介绍..."}
]
current_input = "这个专业的就业前景怎么样？"

print(f"原始输入: {current_input}")
rewritten = semantic_rewrite(chat_history, current_input)
print(f"DeepSeek 重写后: {rewritten}")

# 场景：无上下文（直接补全）
chat_history_empty = []
current_input_vague = "教我做红烧肉"
# 这种情况下模型应该保持原意或微调为标准搜索句
print(f"\n原始输入: {current_input_vague}")
rewritten_vague = semantic_rewrite(chat_history_empty, current_input_vague)
print(f"DeepSeek 重写后: {rewritten_vague}")