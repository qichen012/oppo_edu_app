import os
import time
import json
import fitz
import threading
from datetime import datetime, timezone
from openai import OpenAI
from .config import ZHIZENGZENG_API_KEY, ZHIZENGZENG_BASE_URL, MODEL_NAME, OUTPUT_DIR
from .mem0_manager import upload_card_to_mem0

# 初始化客户端
client = OpenAI(api_key=ZHIZENGZENG_API_KEY, base_url=ZHIZENGZENG_BASE_URL)


def extract_text_fast(pdf_path, max_pages=15):
    """提取PDF文本"""
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            text += page.get_text()
        return text
    except Exception as e:
        print(f"解析PDF错误: {e}")
        return None


def generate_card_json(text):
    """调用 LLM 生成卡片 JSON"""
    system_prompt = """
    你是一个专业编辑。将用户输入的文本转化为用于生成"美观笔记卡片"的JSON数据。
    
    关键要求：
    1. **必须使用中文**：无论输入文档是中文还是英文，输出的 title, summary, key_points, quote 等字段的内容**必须翻译并总结为中文**。
    2. JSON结构必须包含：
    {
        "meta": {"color": "#Hex", "category": "String"},
        "header": {"title": "String", "subtitle": "String"},
        "body": {"summary": "String", "key_points": [{"icon": "String", "text": "String"}]},
        "footer": {"quote": "String"}
    }
    3. 只返回纯 JSON，不要 Markdown 代码块。
    """
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"内容如下：\n{text[:30000]}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"LLM调用错误: {e}")
        return None


def save_local_archive(filename, json_data, upload_to_mem0=True, user_id="user_bupt_01"):
    """
    保存 JSON 到本地文件夹作为归档，并可选上传到 Mem0
    
    Args:
        filename: 文件名
        json_data: JSON 字符串格式的卡片数据
        upload_to_mem0: 是否同时上传到 Mem0，默认 True
        user_id: Mem0 用户ID，默认 user_bupt_01
        
    Returns:
        本地保存路径
    """
    base_name = os.path.splitext(filename)[0]
    save_path = os.path.join(OUTPUT_DIR, f"{base_name}_card.json")
    
    # 保存到本地
    with open(save_path, 'w', encoding='utf-8') as f:
        f.write(json_data)
    
    print(f"💾 本地归档已保存: {save_path}")
    
    # 异步上传到 Mem0（不阻塞主流程）
    if upload_to_mem0:
        def upload_to_mem0_async():
            try:
                card_dict = json.loads(json_data)
                print(f"📤 开始上传到 Mem0 (user_id: {user_id})...")
                mem0_result = upload_card_to_mem0(
                    card_data=card_dict,
                    user_id=user_id,
                    agent_id="pdf_processor"
                )
                if mem0_result:
                    print(f"🧠 Mem0 记忆已创建 (user_id: {user_id})")
            except json.JSONDecodeError:
                print(f"⚠️ JSON 解析失败，跳过 Mem0 上传")
            except Exception as e:
                print(f"⚠️ Mem0 上传异常: {e}")
        
        # 在后台线程中执行上传
        thread = threading.Thread(target=upload_to_mem0_async, daemon=True)
        thread.start()
        print(f"🔄 Mem0 上传已在后台启动...")
    
    return save_path


def process_pdf_file(pdf_path, filename=None, max_pages=15):
    """处理PDF文件的主函数"""
    start_time = time.time()
    raw_text = extract_text_fast(pdf_path, max_pages=max_pages)
    if not raw_text:
        raise RuntimeError("无法从 PDF 中提取文字")

    json_str = generate_card_json(raw_text)
    if not json_str:
        raise RuntimeError("AI 服务响应失败")

    archived_path = save_local_archive(filename or os.path.basename(pdf_path), json_str)

    try:
        parsed = json.loads(json_str)
    except Exception:
        parsed = {"raw_output": json_str, "error": "JSON解析失败，返回原始文本"}

    return {
        "status": "success",
        "process_time": f"{time.time() - start_time:.2f}s",
        "file_name": filename or os.path.basename(pdf_path),
        "archived_at": archived_path,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data": parsed
    }