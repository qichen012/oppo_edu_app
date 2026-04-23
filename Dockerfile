FROM python:3.11

WORKDIR /app

ARG INSTALL_KNOWLEDGE_TREE_DEPS=0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install dependencies first (better layer caching)
COPY requirements.txt /app/requirements.txt

RUN python -m pip install --upgrade pip \
 && pip install --no-cache-dir -r /app/requirements.txt

# Optional: KnowledgeTree / Chroma dependencies (not required for the default run path)
COPY knowledge_tree/requirements.txt /app/knowledge_tree/requirements.txt

RUN if [ "${INSTALL_KNOWLEDGE_TREE_DEPS}" = "1" ]; then \
            pip install --no-cache-dir -r /app/knowledge_tree/requirements.txt; \
        fi

# Copy application code
COPY . /app

# Ensure runtime dirs exist (bind-mounted in compose for persistence)
RUN mkdir -p /app/data /app/chroma_db

EXPOSE 8001

CMD ["python", "run/server.py"]
