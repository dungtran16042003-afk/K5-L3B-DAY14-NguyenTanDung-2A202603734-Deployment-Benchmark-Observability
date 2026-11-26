# ============================================================
# Production Dockerfile — multi-stage, non-root
# ============================================================

# Stage 1: builder — chỉ để cài dependencies
FROM python:3.11-slim AS builder

WORKDIR /build
# Copy requirements trước: sửa code không làm mất cache của lớp pip install
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# Stage 2: runtime — chỉ mang theo thư viện đã cài và code cần chạy
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system app && useradd --system --gid app --no-create-home app

WORKDIR /app
COPY --from=builder /install /usr/local
COPY app/ ./app/
COPY utils/ ./utils/

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT', '8000'), timeout=3)" || exit 1

# exec: uvicorn thay thế shell làm PID 1 nên nhận được SIGTERM từ `docker stop`.
# --timeout-graceful-shutdown 8: chờ request đang chạy, nhưng vẫn kịp trước hạn 10s của docker stop.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2 --timeout-graceful-shutdown 8 --no-access-log"]
