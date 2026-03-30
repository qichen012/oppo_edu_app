"""
ChromaDB 上下文压缩 API 服务
提供 HTTP API 供前端和服务器调用
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime
import uvicorn
import os

# 全局 QA 系统（会懒性初始化）
qa_system = None

def get_qa_system():
    """懒性初始化 QA 系统，避免循环导入"""
    global qa_system
    if qa_system is None:
        from learning_qa import create_qa_system
        qa_system = create_qa_system()
    return qa_system


# 导入 ChromaDB 搜索模块
from chroma_search import (
    ContextualCompressionSearch,
    create_search_instance,
    add_to_chroma,
    search_chroma,
    DEFAULT_COLLECTION,
    DEFAULT_CHROMA_PATH
)

# 尝试导入 LLM 客户端
try:
    from openai import OpenAI

    def get_qwen_client():
        """获取 Qwen LLM 客户端"""
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            env_path = os.path.join(os.path.dirname(__file__), ".env")
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip().startswith("DASHSCOPE_API_KEY"):
                            api_key = line.split("=")[1].strip()
                            break
        if not api_key:
            return None

        ase_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        return OpenAI(api_key=api_key, base_url=ase_url)

    llm_client = get_qwen_client()
except ImportError:
    llm_client = None

# ============ FastAPI 应用 ============
app = FastAPI(
    title="ChromaDB + RAG 问答服务",
    description="提供向量检索、上下文压缩和 RAG 问答功能",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    max_age=3600
)

# 存储搜索实例
_search_instances: Dict[str, ContextualCompressionSearch] = {}


def get_search_instance(collection: str = DEFAULT_COLLECTION) -> ContextualCompressionSearch:
    """获取或创建搜索实例"""
    if collection not in _search_instances:
        _search_instances[collection] = create_search_instance(collection)

    search = _search_instances[collection]

    # 如果有 LLM 客户端，设置它
    if llm_client:
        search.set_llm_client(llm_client)

    return search


def create_response(
    code: int,
    message: str,
    data: Any = None,
    error: str = None
) -> Dict[str, Any]:
    """创建统一的响应格式"""
    response = {
        "code": code,
        "message": message,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    if data is not None:
        response["data"] = data
    if error is not None:
        response["error"] = error
    return response


# ============ 请求/响应模型 ============
class AddDocumentsRequest(BaseModel):
    """添加文档请求"""
    documents: List[str] = Field(..., description="文档内容列表")
    metadatas: Optional[List[Dict]] = Field(default=None, description="元数据列表")
    ids: Optional[List[str]] = Field(default=None, description="ID 列表")
    collection: str = Field(default=DEFAULT_COLLECTION, description="集合名称")


class SearchRequest(BaseModel):
    """搜索请求"""
    query: str = Field(..., description="查询文本")
    nResults: int = Field(default=5, ge=1, le=100, description="返回结果数量")
    collection: str = Field(default=DEFAULT_COLLECTION, description="集合名称")
    where: Optional[Dict] = Field(default=None, description="元数据过滤条件")


class CompressionSearchRequest(BaseModel):
    """压缩搜索请求"""
    query: str = Field(..., description="查询文本")
    nResults: int = Field(default=10, ge=1, le=100, description="初始检索数量")
    nAfterCompression: int = Field(default=5, ge=1, le=50, description="压缩后保留数量")
    compressionStrategy: str = Field(
        default="keyword",
        description="压缩策略: keyword/extractor/filter"
    )
    collection: str = Field(default=DEFAULT_COLLECTION, description="集合名称")


class DeleteDocumentsRequest(BaseModel):
    """删除文档请求"""
    ids: List[str] = Field(..., description="要删除的文档 IDs")
    collection: str = Field(default=DEFAULT_COLLECTION, description="集合名称")


class QARequest(BaseModel):
    """RAG 问答请求"""
    sessionId: str = Field(..., description="会话 ID")
    query: str = Field(..., description="用户问题")
    nLearningResults: int = Field(default=3, ge=1, le=10, description="学习分析结果数")
    nQaResults: int = Field(default=5, ge=1, le=10, description="QA 结果数")
    saveAnalysis: bool = Field(default=True, description="是否保存分析")


# ============ 响应模型 ============

class DocumentResponse(BaseModel):
    """文档操作响应"""
    code: int
    message: str
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class SearchResponse(BaseModel):
    """搜索响应"""
    code: int
    message: str
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class CompressionSearchResponse(BaseModel):
    """压缩搜索响应"""
    code: int
    message: str
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class QAResponse(BaseModel):
    """RAG 问答响应"""
    code: int
    message: str
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


# ============ API 端点 ============

@app.get("/health")
def health_check():
    """健康检查端点"""
    return create_response(200, "healthy")


@app.post("/api/v1/documents/add")
def add_documents(request: AddDocumentsRequest):
    """
    添加文档到向量库
    
    Args:
        request: 包含文档内容和元数据的请求
    
    Returns:
        添加结果，包括生成的 ID 和文档总数
        
    Raises:
        HTTPException: 400 - 参数验证失败，500 - 添加失败
    """
    try:
        search = get_search_instance(request.collection)
        ids = search.add_documents(
            documents=request.documents,
            metadatas=request.metadatas,
            ids=request.ids
        )
        return create_response(
            200,
            "success",
            {
                "ids": ids,
                "count": search.get_document_count(),
                "collection": request.collection
            }
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=create_response(400, str(e), error="INVALID_PARAM")
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=create_response(500, "添加文档失败", error="DATABASE_ERROR")
        )


@app.post("/api/v1/documents/delete")
def delete_documents(request: DeleteDocumentsRequest):
    """删除指定 ID 的文档"""
    try:
        search = get_search_instance(request.collection)
        search.delete_documents(request.ids)
        return create_response(
            200,
            "success",
            {
                "deletedCount": len(request.ids),
                "collection": request.collection
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=create_response(500, "删除文档失败", error="DATABASE_ERROR")
        )


@app.post("/api/v1/documents/clear")
def clear_collection(collection: str = Query(DEFAULT_COLLECTION)):
    """清空集合中的所有文档"""
    try:
        search = get_search_instance(collection)
        search.clear_collection()
        return create_response(
            200,
            "success",
            {"collection": collection, "message": "集合已清空"}
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=create_response(500, "清空集合失败", error="DATABASE_ERROR")
        )


@app.get("/api/v1/documents/count")
def get_document_count(collection: str = Query(DEFAULT_COLLECTION)):
    """获取文档数量"""
    try:
        search = get_search_instance(collection)
        return create_response(
            200,
            "success",
            {"count": search.get_document_count(), "collection": collection}
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=create_response(500, "获取文档数量失败", error="DATABASE_ERROR")
        )


# ============ 搜索端点 ============

@app.post("/api/v1/search/basic")
def search(request: SearchRequest):
    """
    基础向量搜索
    
    Args:
        request: 搜索请求，包含查询文本和结果数量
    
    Returns:
        匹配的文档和距离分数
    """
    try:
        search = get_search_instance(request.collection)
        result = search.search(
            query=request.query,
            n_results=request.nResults,
            where=request.where
        )
        return create_response(
            200,
            "success",
            {
                "query": result.query,
                "documents": result.documents,
                "distances": result.distances,
                "metadatas": result.metadatas,
                "ids": result.ids,
                "collection": request.collection
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=create_response(500, "搜索失败", error="DATABASE_ERROR")
        )


@app.post("/api/v1/search/compression")
def compression_search(request: CompressionSearchRequest):
    """
    带上下文压缩的智能搜索
    
    Args:
        request: 包含查询文本和压缩策略的请求
    
    Returns:
        经过压缩处理的搜索结果
    """
    try:
        search = get_search_instance(request.collection)
        result = search.search_with_context(
            query=request.query,
            n_results=request.nResults,
            n_after_compression=request.nAfterCompression,
            compression_strategy=request.compressionStrategy
        )
        return create_response(
            200,
            "success",
            {
                "query": request.query,
                "documents": result.documents,
                "scores": result.scores,
                "originalDocuments": result.original_documents,
                "collection": request.collection
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=create_response(500, "压缩搜索失败", error="DATABASE_ERROR")
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=create_response(500, "压缩搜索失败", error="DATABASE_ERROR")
        )


@app.get("/api/v1/collections")
def list_collections():
    """列出所有集合"""
    try:
        from chroma_search import get_chroma_client
        client = get_chroma_client()
        collections = client.list_collections()
        return create_response(
            200,
            "success",
            {"collections": [c.name for c in collections]}
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=create_response(500, "获取集合列表失败", error="DATABASE_ERROR")
        )


# ============ RAG 问答端点 ============
qa_sessions: Dict[str, Any] = {}

def get_session_qa(session_id: str):
    """获取或创建会话的 QA 系统"""
    if session_id not in qa_sessions:
        qa_sessions[session_id] = get_qa_system()
    return qa_sessions[session_id]


@app.post("/api/v1/qa/ask")
def qa_ask(request: QARequest):
    """
    RAG 问答接口
    
    根据用户问题，结合学习分析历史和知识库进行智能问答。
    
    Args:
        request: 包含会话ID、问题和检索参数的请求
    
    Returns:
        问答结果、学习分析和相关上下文
        
    Raises:
        HTTPException: 500 - 问答处理失败
    """
    try:
        qa = get_session_qa(request.sessionId)
        result = qa.answer(
            query=request.query,
            n_learning_results=request.nLearningResults,
            n_qa_results=request.nQaResults,
            save_analysis=request.saveAnalysis
        )
        return create_response(
            200,
            "success",
            {
                "sessionId": request.sessionId,
                "query": result.get("query", request.query),
                "answer": result.get("answer", ""),
                "learningAnalysis": result.get("learning_analysis"),
                "analysisId": result.get("analysis_id"),
                "learningContext": result.get("learning_context"),
                "qaContext": result.get("qa_context")
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=create_response(500, "问答失败", error="MODEL_ERROR")
        )


# ============ 启动服务 ============
if __name__ == "__main__":
    port = int(os.getenv("KNOWLEDGE_PORT", "8002"))
    print(f"🚀 ChromaDB + RAG 问答服务启动在 http://0.0.0.0:{port}")
    print(f"📖 API 文档: http://0.0.0.0:{port}/docs")
    uvicorn.run(app, host="0.0.0.0", port=port)
