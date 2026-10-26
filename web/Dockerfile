# 科研出图工具 Web（FastAPI）
# 构建上下文必须是 research-tools 根目录：
#   docker build -f web/Dockerfile -t research-tools-web:0.3 .
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    RESEARCH_TOOLS_JOBS=/tmp/research-tools-jobs

WORKDIR /app

# 系统依赖：常见科学绘图 + CJK 可选字体
RUN apt-get update && apt-get install -y --no-install-recommends \
      fonts-dejavu-core \
      fonts-noto-cjk \
      libfreetype6 \
      libpng16-16 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
COPY web/requirements.txt /app/web/requirements.txt
RUN pip install --upgrade pip \
 && pip install -r /app/requirements.txt -r /app/web/requirements.txt

# 整个 research-tools 树（含 lib / eis_* / demo 等）
COPY . /app/

RUN mkdir -p /tmp/research-tools-jobs \
 && useradd -m -u 10001 appuser \
 && chown -R appuser:appuser /app /tmp/research-tools-jobs

USER appuser
WORKDIR /app/web
EXPOSE 8766

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8766/health', timeout=3)"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8766"]
