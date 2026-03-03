import os
import sys
import time
import json
import shutil
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


@app.post("/analyze_screenshot")
async def analyze_screenshot(file: UploadFile = File(...)):
    """上传截图 -> 与本地笔记库对比（逻辑委托给 skill.ai_handlers）"""
    try:
        image_bytes = await file.read()
        result = analyze_screenshot_bytes(image_bytes)
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


# 启动命令提示
if __name__ == "__main__":
    print("启动服务中... 请在浏览器访问 http://127.0.0.1:8001/docs 查看接口文档")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)