import os
import sys
import time
import json
import shutil
from datetime import date, timedelta
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from skill.pdf_processor import process_pdf_file
from skill.lecture_handout_generator import process_pdf_to_handout
from skill.screenshot_analyzer import analyze_screenshot_bytes
from skill.recommendation_engine import analyze_user_profile, generate_recommendations
from skill.meeting_transcriber import transcribe_audio_file
from skill.query_rewriter import semantic_rewrite
from skill.chat_manager import create_chat_session
from skill.config import UPLOAD_DIR
from skill.ebbinghaus_recommender import recommend_ebbinghaus_brief
from skill.elite_ideas_extractor import process_pdf_to_elite_ideas
from skill.daily_briefing_generator import generate_daily_briefing, update_daily_briefing, load_daily_briefing, get_briefs_to_review


# 确保项目根目录在 sys.path 中
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


# 初始化 FastAPI
app = FastAPI(title="PDF to NoteCard API")


# ===== 数据模型定义 =====
class UserHistory(BaseModel):
    title: str
    clicks: int
    duration: float
    tags: List[str]


class UserProfileRequest(BaseModel):
    user_history: List[UserHistory]


class RecommendRequest(BaseModel):
    user_history: List[Dict[str, Any]]  # 兼容 [{"brief_id": 1, "last_view_time": 1670000000}]
    total_briefs: int = 100  # 简报总数（默认100，可由前端或数据库传入）
    limit: int = 3  # 推荐返回的数量 (Top-K)
    source: str = 'rss'  # 'rss' or 'ddgs'
    epsilon: float = 0.1


class QueryRewriteRequest(BaseModel):
    history: List[Dict[str, str]]  # [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    current_query: str


class ChatRequest(BaseModel):
    user_id: str
    message: str
    system_prompt: str = None  # 可选的系统提示词


class ChatHistoryRequest(BaseModel):
    user_id: str
    limit: int = None  # 限制返回的消息数量


class DailyBriefingRequest(BaseModel):
    user_id: int                  # 用户 ID（对应 DB users.id）
    target_date: str = None       # 目标日期 "YYYY-MM-DD"，默认今天


class UpdateBriefingRequest(BaseModel):
    user_id: int                  # 用户 ID
    user_reflect: str             # 用户在 App 端输入的补充内容/心得
    target_date: str = None       # 目标日期，默认今天


@app.post("/process_pdf")
async def process_pdf(file: UploadFile = File(...)):
    """上传 PDF 文件 -> 返回 卡片 JSON（逻辑委托给 skill.ai_handlers）"""
    start_time = time.time()

    file_path = os.path.join(UPLOAD_DIR, file.filename)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件上传失败: {e}")

    try:
        result = process_pdf_file(file_path, filename=file.filename)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate_handout")
async def generate_handout(file: UploadFile = File(...)):
    """上传 PDF 文件 -> 返回结构化讲义 JSON + Markdown 文本"""
    start_time = time.time()

    file_path = os.path.join(UPLOAD_DIR, file.filename)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件上传失败: {e}")

    try:
        result = process_pdf_to_handout(file_path, filename=file.filename)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/extract_elite_ideas")
async def extract_elite_ideas(file: UploadFile = File(...)):
    """上传 PDF 文件 -> 提取 Elite Ideas（跨领域深层洞见）"""
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件上传失败: {e}")

    try:
        result = process_pdf_to_elite_ideas(
            file_path, 
            filename=file.filename,
            save_to_file=True  # 默认保存到文件
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze_screenshot")
async def analyze_screenshot(file: UploadFile = File(...)):
    """上传截图 -> 与本地笔记库对比，截图保存到 images/，分析结果保存到 analysis/"""
    try:
        image_bytes = await file.read()

        data_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "data_screenshot"))
        images_dir = os.path.join(data_root, "images")
        analysis_dir = os.path.join(data_root, "analysis")
        os.makedirs(images_dir, exist_ok=True)
        os.makedirs(analysis_dir, exist_ok=True)

        ts = int(time.time())
        base_name = os.path.splitext(file.filename)[0] if file.filename else "screenshot"
        ext = os.path.splitext(file.filename)[1] if file.filename else ".png"

        # 保存原始截图
        image_save_path = os.path.join(images_dir, f"{ts}_{base_name}{ext}")
        with open(image_save_path, "wb") as f:
            f.write(image_bytes)
        print(f"📸 截图已保存: {image_save_path}")

        # 调用分析
        result = analyze_screenshot_bytes(image_bytes)

        # 保存分析结果 JSON
        analysis_save_path = os.path.join(analysis_dir, f"{ts}_{base_name}_analysis.json")
        with open(analysis_save_path, "w", encoding="utf-8") as f:
            json.dump({
                "source_file": file.filename,
                "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "image_path": image_save_path,
                **result
            }, f, ensure_ascii=False, indent=2)
        print(f"📝 分析结果已保存: {analysis_save_path}")

        result["image_path"] = image_save_path
        result["analysis_archived_at"] = analysis_save_path
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze_profile")
async def analyze_profile(request: UserProfileRequest):
    """分析用户行为数据，生成用户画像"""
    try:
        user_history = [item.dict() for item in request.user_history]
        result = analyze_user_profile(user_history)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/recommend")
async def recommend_content(request: RecommendRequest):
    """基于用户历史生成推荐内容（艾宾浩斯曲线）"""
    try:
        # 提取用户历史
        user_history = request.user_history
        
        # 调用改进版艾宾浩斯推荐算法
        recommend_ids = recommend_ebbinghaus_brief(
            user_history=user_history, 
            total_briefs=request.total_briefs, 
            top_k=request.limit
        )
        
        return {
            "recommend_brief_ids": recommend_ids,
            "success": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/meeting_transcribe")
async def meeting_transcribe(file: UploadFile = File(...)):
    """接收音频文件，转发到转录服务器，返回会议纪要"""
    # 临时保存上传的音频文件
    temp_audio_path = os.path.join(UPLOAD_DIR, f"temp_audio_{int(time.time())}_{file.filename}")
    
    try:
        # 保存上传的音频文件
        with open(temp_audio_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 调用 skill 模块处理转录
        result = transcribe_audio_file(temp_audio_path)
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 清理临时文件
        if os.path.exists(temp_audio_path):
            try:
                os.remove(temp_audio_path)
            except:
                pass


@app.post("/query_rewrite")
async def query_rewrite(request: QueryRewriteRequest):
    """对用户查询进行语义重写，融合上下文信息"""
    try:
        rewritten_query = semantic_rewrite(request.history, request.current_query)
        return {
            "original_query": request.current_query,
            "rewritten_query": rewritten_query,
            "success": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
async def chat(request: ChatRequest):
    """与 AI 对话，自动维护上下文记忆"""
    try:
        # 创建或获取用户的对话会话
        chat_manager = create_chat_session(request.user_id)
        
        # 发送消息并获取回复
        response = chat_manager.chat(
            user_message=request.message,
            system_prompt=request.system_prompt
        )
        
        return {
            "user_id": request.user_id,
            "user_message": request.message,
            "ai_response": response,
            "success": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/history")
async def get_chat_history(request: ChatHistoryRequest):
    """获取用户的对话历史"""
    try:
        chat_manager = create_chat_session(request.user_id)
        history = chat_manager.get_history(limit=request.limit)
        
        return {
            "user_id": request.user_id,
            "history": history,
            "total_messages": len(history),
            "success": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/clear")
async def clear_chat_history(request: ChatHistoryRequest):
    """清空用户的对话历史"""
    try:
        chat_manager = create_chat_session(request.user_id)
        chat_manager.clear_history()
        
        return {
            "user_id": request.user_id,
            "message": "对话历史已清空",
            "success": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate_daily_briefing")
async def api_generate_daily_briefing(request: DailyBriefingRequest):
    """
    基于当天已处理的 PDF 讲义，生成每日简报。

    返回字段与 DB schema 完全对齐，可直接写入 daily_briefs 表：
    - posterior_insight : 约150字封面摘要（封面页展示）
    - key_concepts      : 简报全文（详情页展示）
    - target_date       : 简报所属日期
    - next_review_date  : Ebbinghaus 首次复习日期（明天）
    - review_stage      : 0（刚生成）
    - user_reflect      : 空字符串（用户后续填写）
    - source_handouts   : 当天参与合成的讲义标题列表
    """
    try:
        result = generate_daily_briefing(
            user_id=request.user_id,
            target_date=request.target_date,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_daily_briefing")
async def api_get_daily_briefing(user_id: int, target_date: str = None):
    """获取指定日期的每日简报（直接读本地文件，不重新生成）"""
    try:
        result = load_daily_briefing(user_id=user_id, target_date=target_date)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/update_daily_briefing")
async def api_update_daily_briefing(request: UpdateBriefingRequest):
    """
    融合用户补充内容，更新今日简报。

    流程：读取原简报 → AI 融合用户反思 → 更新 posterior_insight / key_concepts
          → 写入 user_reflect → 覆盖保存文件 → 返回完整更新后的简报

    返回格式与 /generate_daily_briefing 完全一致，额外包含：
    - updated_at: 本次更新时间
    - user_reflect: 用户输入内容（已写入）
    """
    try:
        result = update_daily_briefing(
            user_id=request.user_id,
            user_reflect=request.user_reflect,
            target_date=request.target_date,
        )
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/daily_briefing/review_list")
async def api_get_briefs_to_review(user_id: int, check_date: str = None):
    """
    获取今日最需要复习的简报（逾期天数最多的那一份）。
    无待复习简报时返回 {"brief": null, "due_count": 0}。
    容错：若推荐系统出错，兜底返回3天前的简报（若存在）。
    """
    try:
        candidate = get_briefs_to_review(user_id=user_id, check_date=check_date)
        # 用 target_date 加载完整简报 JSON
        brief = load_daily_briefing(user_id=user_id, target_date=candidate["target_date"]) if candidate else None
        return {
            "user_id": user_id,
            "check_date": check_date or date.today().isoformat(),
            "due_count": 1 if brief else 0,
            "brief": brief,
            "fallback": False,
        }
    except Exception as e:
        print(f"⚠️ 推荐系统异常，启用兜底策略: {e}")
        # 兜底：返回3天前的简报
        try:
            fallback_date = (date.today() - timedelta(days=3)).isoformat()
            brief = load_daily_briefing(user_id=user_id, target_date=fallback_date)
            return {
                "user_id": user_id,
                "check_date": check_date or date.today().isoformat(),
                "due_count": 1,
                "brief": brief,
                "fallback": True,
                "fallback_reason": str(e),
            }
        except Exception:
            return {
                "user_id": user_id,
                "check_date": check_date or date.today().isoformat(),
                "due_count": 0,
                "brief": None,
                "fallback": True,
                "fallback_reason": str(e),
            }


# 启动命令提示
if __name__ == "__main__":
    print("启动服务中... 请在浏览器访问 http://127.0.0.1:8001/docs 查看接口文档")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)