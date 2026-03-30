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


def extract_all_info_from_screenshot_bytes(image_bytes):
        """提取截图中的全部可识别信息（OCR、结构、要点、问题与行动项）"""
        start_time = time.time()
        base64_image = encode_image(image_bytes)

        system_prompt = """
        你是一个严谨的信息抽取引擎。用户会上传一张截图。

        你的任务：尽可能完整地提取截图中的信息，并输出结构化 JSON。

        输出要求：
        1. 不要虚构看不到的内容；看不清请标注 uncertain。
        2. OCR 文本尽量保留原文顺序与标点。
        3. 对界面元素给出类型与位置信息（粗粒度即可：top/center/bottom + left/center/right）。
        4. 如果有表格、列表、公式、代码、图表，请分别提取。

        请严格返回以下 JSON 结构：
        {
            "summary": "一句话总结截图主要内容",
            "language": "zh|en|mixed|unknown",
            "ocr_text": "完整可读文本，按阅读顺序拼接",
            "entities": {
                "people": [],
                "organizations": [],
                "products": [],
                "technologies": [],
                "dates": [],
                "numbers": [],
                "urls": [],
                "emails": []
            },
            "layout_elements": [
                {
                    "type": "title|paragraph|button|input|menu|table|chart|code|image|icon|other",
                    "position": "top-left|top-center|top-right|center-left|center|center-right|bottom-left|bottom-center|bottom-right",
                    "text": "该区域核心文本",
                    "confidence": "high|medium|low"
                }
            ],
            "structured_content": {
                "lists": [],
                "tables": [],
                "code_blocks": [],
                "equations": [],
                "chart_insights": []
            },
            "tasks_or_actions": [],
            "questions_or_issues": [],
            "sensitive_info_detected": {
                "has_sensitive": false,
                "types": []
            },
            "uncertain": []
        }
        """

        print("🧾 正在提取截图中的全量信息...")

        try:
                response = client.chat.completions.create(
                        model=MODEL_NAME,
                        messages=[
                                {"role": "system", "content": system_prompt},
                                {
                                        "role": "user",
                                        "content": [
                                                {"type": "text", "text": "请提取这张截图中的所有可识别信息，并按约定 JSON 返回。"},
                                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                                        ]
                                }
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.1
                )

                extract_result = response.choices[0].message.content
                return {
                        "status": "success",
                        "process_time": f"{time.time() - start_time:.2f}s",
                        "data": json.loads(extract_result)
                }
        except Exception as e:
                print(f"全量提取失败: {e}")
                raise


def analyze_screenshot_brief_association(extracted_info: dict, daily_brief: dict):
    """基于已保存的截图提取结果与每日简报做关联分析（不重复做视觉识别）"""
    start_time = time.time()

    system_prompt = """
    你是一个学习关联分析引擎。

    输入包含两部分：
    1) 截图的结构化提取结果（已由视觉模型生成）
    2) 每日简报（posterior_insight + key_concepts）

    你的任务：识别截图与每日简报之间的高价值关联，输出 JSON。

    请严格返回：
    {
      "overall_relevance": "high|medium|low",
      "association_summary": "一句话总结关联结论",
      "matched_points": [
        {
          "screenshot_evidence": "截图中的证据",
          "brief_evidence": "简报中的对应证据",
          "reason": "为什么构成关联"
        }
      ],
      "unmatched_points": ["截图中但简报未覆盖的要点"],
      "suggested_updates": ["建议补充到简报中的内容"],
      "confidence": "high|medium|low"
    }
    """

    user_payload = {
        "screenshot_extracted_info": extracted_info,
        "daily_brief": {
            "target_date": daily_brief.get("target_date"),
            "posterior_insight": daily_brief.get("posterior_insight", ""),
            "key_concepts": daily_brief.get("key_concepts", ""),
            "source_handouts": daily_brief.get("source_handouts", []),
        },
    }

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"请做截图与每日简报关联分析：\n{json.dumps(user_payload, ensure_ascii=False)}",
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )

        association_result = response.choices[0].message.content
        return {
            "status": "success",
            "process_time": f"{time.time() - start_time:.2f}s",
            "data": json.loads(association_result),
        }
    except Exception as e:
        print(f"关联分析失败: {e}")
        raise