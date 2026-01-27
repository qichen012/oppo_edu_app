FROM python:3.12

# 1. 基础目录
WORKDIR /app

# 2. 安装基础依赖
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. 安装 mem0（非 editable，最稳）
WORKDIR /tmp/mem0
COPY pyproject.toml .
COPY poetry.lock .
COPY README.md .
COPY mem0 ./mem0

RUN pip install --no-cache-dir .[graph]

# 4. 拷贝 server 代码
WORKDIR /app
COPY server .

# 5. 启动
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
