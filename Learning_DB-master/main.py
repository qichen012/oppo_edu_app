import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from routers import api_router
from database import engine, Base

app = FastAPI(
    title="Learning Management System API",
    description="A comprehensive learning management system API for educational platform",
    version="1.0.0"
)


@app.on_event("startup")
async def _startup_init_db() -> None:
    """等待 DB 就绪后再建表，避免 docker compose 启动顺序导致的连接拒绝。"""

    max_retries = 30
    delay_seconds = 2

    last_exc: Exception | None = None
    for _ in range(max_retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            Base.metadata.create_all(bind=engine)
            return
        except OperationalError as e:
            last_exc = e
            await asyncio.sleep(delay_seconds)
        except Exception as e:
            last_exc = e
            await asyncio.sleep(delay_seconds)

    # 重试耗尽仍失败，让容器直接退出（compose 会重启），方便尽快暴露问题
    raise RuntimeError(f"Database not ready after retries: {last_exc}")

# 配置CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应限制为特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册API路由器
app.include_router(api_router, prefix="/api/v1")

@app.get("/")
def read_root():
    return {"message": "Welcome to Learning Management System API"}