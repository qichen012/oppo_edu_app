import os
import time
import json
import glob
import base64
from openai import OpenAI
from .config import ZHIZENGZENG_API_KEY, ZHIZENGZENG_BASE_URL, MODEL_NAME, OUTPUT_DIR

# 初始化客户端
client = OpenAI(api_key=ZHIZENGZENG_API_KEY, base_url=ZHIZENGZENG_BASE_URL)

    
def load_all_notes_context(notes_dir):
    """加载所有笔记的上下文信息"""
    context_list = []
    files = glob.glob(os.path.join(notes_dir, "*_card.json"))
    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                note_info = {
                    "filename": os.path.basename(file_path),
                    "title": data.get("header", {}).get("title", "无标题"),
                    "summary": data.get("body", {}).get("summary", ""),
                    "keywords": data.get("body", {}).get("keywords", [])
                }
                context_list.append(note_info)
        except Exception as e:
            print(f"跳过损坏的文件 {file_path}: {e}")
    return context_list


def encode_image(image_bytes):
    """将图片字节转换为 Base64 字符串"""
    return base64.b64encode(image_bytes).decode('utf-8')


def analyze_screenshot_bytes(image_bytes):
    """分析截图并与笔记库进行关联"""
    start_time = time.time()
    base64_image = encode_image(image_bytes)
    notes_context = load_all_notes_context(OUTPUT_DIR)
    
    if not notes_context:
        return {"status": "warning", "message": "笔记库为空，无法进行关联分析。"}

    context_str = json.dumps(notes_context, ensure_ascii=False, indent=2)

    system_prompt = """
    你是一个深度思考的知识关联引擎。用户会上传一张"屏幕截图"和一系列"历史笔记上下文"。
    
    你的核心任务是：**寻找最佳的原理性关联 (Best Conceptual or Structural Match)**。
    
    请执行以下逻辑：
    1. **深度抽象**：不要只看截图表面的文字或图像，要分析它背后的**底层逻辑、抽象模型、数学原理或思维方式**。
    2. **宽泛匹配**：在历史笔记中寻找关联。
       - ✅ **直接关联**：内容直接相关（如：截图是代码，笔记是该代码的解释）。
       - ✅ **原理相似**：表面看似无关，但底层机制一致（**重点关注**）。
    
    请返回 JSON 格式：
    {
        "screenshot_analysis": "截图内容的本质分析（不仅仅是描述画面，要提炼原理）",
        "best_match": {
            "related_note_filename": "xxx_card.json",
            "note_title": "笔记标题",
            "reason": "请详细说明两者的'原理相似性'"
        }
    }
    
    注意：如果实在找不到任何层面的关联，"best_match" 返回 null。
    """

    print("🧠 正在进行视觉分析与知识库比对...")
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"这是我的历史笔记库数据：\n{context_str}\n\n请分析下面这张截图，找出它和我的笔记库有什么关联？"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.3
        )

        analysis_result = response.choices[0].message.content
        return {
            "status": "success", 
            "process_time": f"{time.time() - start_time:.2f}s", 
            "data": json.loads(analysis_result)
        }

    except Exception as e:
        print(f"分析失败: {e}")
        raise