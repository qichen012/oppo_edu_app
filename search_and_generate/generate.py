try:
    from .api import get_qwen_client
except ImportError:  # 兼容：直接运行脚本
    from api import get_qwen_client



def generate_expansion(concept, search_results=None):
    """生成函数：使用Qwen模型进行扩写"""
    if not concept:
        return "未提供课内概念，无法进行扩写。"
    
    
    print(f"📝 [生成] 正在使用Qwen模型生成扩写内容...")
    
    client = get_qwen_client()
    
    sources = []
    if isinstance(search_results, list):
        for item in search_results[:5]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "") or "").strip()
            url = str(item.get("url", "") or "").strip()
            if title or url:
                sources.append(f"- {title} {url}".strip())
    sources_text = "\n".join(sources) if sources else "- （无）"
    
    prompt_text = f"""你是一位教育助手，请根据以下课内概念，写一段联系现实的扩写内容。

课内概念：{concept}

要求：
1. 写一段连贯的文字（100字左右）
2. 简要介绍这个概念的定义
3. 结合搜索到的现实案例说明这个概念在实际中的应用或意义
4. 语言要通俗易懂，适合大学生阅读
5. 在最后标注"参考来源："并列出文章标题/链接

可用参考来源（供你挑选/概括，不要求逐字引用）：
{sources_text}

请直接输出扩写内容："""
    try:
        if client:
            resp = client.chat.completions.create(
                model="qwen-plus",
                messages=[
                    {"role": "system", "content": "你是一位专业的教育助手，擅长将知识与现实联系起来。"},
                    {"role": "user", "content": prompt_text}
                ],
                temperature=0.7,
                max_tokens=800
            )
            result_text = (resp.choices[0].message.content or "").strip()
            if not result_text:
                return "生成结果为空"
            print("✅ Qwen生成完成")
            return result_text
        else:
            return "⚠️ 未找到Qwen API Key（DASHSCOPE_API_KEY），无法生成扩写。"
            
    except Exception as e:
        return f"❌ Qwen调用失败: {e}"
