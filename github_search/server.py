from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from github_search import search_github_projects
from typing import Dict, Any, Optional, List
from datetime import datetime
import os

app = FastAPI(
    title="GitHub 开源项目搜索服务",
    description="提供 GitHub 开源项目搜索和推荐功能",
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


@app.get("/health")
def health_check():
    """健康检查端点"""
    return create_response(200, "healthy")


@app.get("/opensource/projects")
def get_open_source_projects(
    keyword: str = Query(..., description="搜索关键词，例如 android/ai/llm"),
    language: str = Query("", description="编程语言"),
    pageNum: int = Query(1, ge=1, description="页码"),
    pageSize: int = Query(10, ge=1, le=100, description="每页数量")
):
    """
    搜索 GitHub 开源项目
    
    Args:
        keyword: 搜索关键词
        language: 编程语言过滤
        pageNum: 页码（从 1 开始）
        pageSize: 每页显示数量
    
    Returns:
        匹配的开源项目列表和分页信息
        
    Raises:
        HTTPException: 400 - 参数验证失败，500 - 搜索失败
    """
    try:
        if not keyword or len(keyword.strip()) == 0:
            raise ValueError("搜索关键词不能为空")
        
        if pageNum < 1 or pageSize < 1:
            raise ValueError("页码和每页数量必须大于 0")
        
        # 调用搜索函数
        projects = search_github_projects(
            concept=keyword,
            language=language,
            per_page=pageSize
        )
        
        # 分页处理
        start_idx = (pageNum - 1) * pageSize
        end_idx = start_idx + pageSize
        paginated_projects = projects[start_idx:end_idx]
        
        return create_response(
            200,
            "success",
            {
                "keyword": keyword,
                "language": language,
                "pageNum": pageNum,
                "pageSize": pageSize,
                "total": len(projects),
                "projects": paginated_projects
            }
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=create_response(400, str(e), error="INVALID_PARAM")
        )
    except Exception as e:
        print(f"❌ 搜索失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=create_response(500, "搜索失败", error="SEARCH_ERROR")
        )


# ============ 启动服务 ============
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("GITHUB_PORT", 8003))
    print(f"🚀 GitHub 搜索服务启动在 http://0.0.0.0:{port}")
    print(f"📖 API 文档: http://0.0.0.0:{port}/docs")
    uvicorn.run(app, host="0.0.0.0", port=port)