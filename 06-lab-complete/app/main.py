"""
Production AI Agent — Part 6 Final Project

Luồng của POST /ask:
    API key (401) → kiểm tra input (422) → rate limit (429) → budget (402)
    → gọi LLM → ghi chi phí → trả lời

Kiểm tra: python check_production_ready.py
"""
import json
import logging
import signal
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from redis import RedisError

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import ask as llm_ask


# ─────────────────────────────────────────────────────────
# Structured logging — mỗi dòng log của app là 1 JSON object
# ─────────────────────────────────────────────────────────
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
            **getattr(record, "fields", {}),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(JsonFormatter())
logger = logging.getLogger("agent")
logger.handlers = [_handler]
logger.setLevel(logging.INFO)
logger.propagate = False  # tránh in lặp qua root logger với format khác


def log(event: str, level: int = logging.INFO, exc_info=None, **fields) -> None:
    logger.log(level, event, extra={"fields": fields}, exc_info=exc_info)


# ─────────────────────────────────────────────────────────
# Graceful shutdown
# ─────────────────────────────────────────────────────────
START_TIME = time.time()
_shutting_down = False


def _install_sigterm_hook() -> None:
    """Ghi log và hạ readiness khi nhận SIGTERM, rồi chuyển tiếp cho handler của uvicorn."""
    if threading.current_thread() is not threading.main_thread():
        return  # signal chỉ đăng ký được từ main thread
    previous = signal.getsignal(signal.SIGTERM)

    def on_sigterm(signum, frame):
        global _shutting_down
        _shutting_down = True
        log("sigterm_received")
        if callable(previous):
            previous(signum, frame)  # không gọi lại thì uvicorn không bao giờ tắt

    signal.signal(signal.SIGTERM, on_sigterm)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _install_sigterm_hook()
    log("startup", environment=settings.environment, port=settings.port)
    if not settings.agent_api_key:
        log("agent_api_key_missing", level=logging.WARNING,
            detail="mọi request /ask sẽ bị 401 cho tới khi đặt AGENT_API_KEY")
    yield
    # uvicorn chỉ chạy tới đây sau khi các request đang xử lý đã xong
    r.close()
    log("shutdown_complete")


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


# ─────────────────────────────────────────────────────────
# Log request + xử lý lỗi: client nhận mã lỗi rõ ràng, không lộ stack trace
# ─────────────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:  # lỗi ngoài dự kiến: stack trace chỉ nằm trong log
        log("unhandled_error", level=logging.ERROR, exc_info=True, request_id=request_id)
        response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
    response.headers["X-Request-ID"] = request_id
    # Không log header hay nội dung câu hỏi: tránh lộ API key và dữ liệu người dùng
    log("request", request_id=request_id, method=request.method, path=request.url.path,
        status=response.status_code, ms=round((time.perf_counter() - start) * 1000, 1))
    return response


@app.exception_handler(RequestValidationError)
async def on_validation_error(request: Request, exc: RequestValidationError):
    # Chỉ trả vị trí và lý do sai, không gửi ngược lại dữ liệu client đã gửi
    errors = [{"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")}
              for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(RedisError)
async def on_redis_error(request: Request, exc: RedisError):
    # Không kiểm tra được rate limit / budget thì không gọi LLM
    log("redis_error", level=logging.ERROR, error=type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "Service temporarily unavailable"})


# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    # Cắt khoảng trắng đầu cuối: câu hỏi chỉ toàn dấu cách bị coi là rỗng
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = Field(default=None, max_length=128)


@app.get("/health")
def health():
    """Liveness: process còn chạy là 200, không phụ thuộc Redis."""
    return {"status": "ok", "uptime_seconds": round(time.time() - START_TIME, 1)}


@app.get("/ready")
def ready():
    """Readiness: chỉ nhận traffic khi dùng được Redis và không đang tắt."""
    if _shutting_down:
        raise HTTPException(status_code=503, detail="Shutting down")
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return {"status": "ready"}


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)  # mock LLM không trả usage: ước lượng ~4 ký tự/token


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)
    check_budget()
    answer = llm_ask(body.question)
    input_tokens = _estimate_tokens(body.question)
    output_tokens = _estimate_tokens(answer)
    cost = record_cost(input_tokens, output_tokens)
    log("llm_call", input_tokens=input_tokens, output_tokens=output_tokens,
        cost_usd=round(cost, 8))
    return {"question": body.question, "answer": answer}
