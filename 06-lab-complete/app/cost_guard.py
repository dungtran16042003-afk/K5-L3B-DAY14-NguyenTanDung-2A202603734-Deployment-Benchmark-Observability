"""
Cost guard (tiêu chí 8).

  • Cộng dồn chi phí LLM (tính theo token) vào Redis, mỗi ngày (UTC) một key
  • Tổng chi phí trong ngày đạt DAILY_BUDGET_USD → HTTP 402

Giới hạn đã biết: kiểm tra trước, ghi chi phí sau, nên các request chạy song song
có thể làm vượt ngân sách một ít (tối đa bằng chi phí của số request đang chạy).
"""
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

# Giữ key 2 ngày để còn xem lại số của hôm trước, sau đó Redis tự xoá
KEY_TTL_SECONDS = 2 * 24 * 3600


def _today_key() -> str:
    return f"cost:{datetime.now(timezone.utc):%Y-%m-%d}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → HTTP 402."""
    spent = float(r.get(_today_key()) or 0)
    if spent >= settings.daily_budget_usd:
        raise HTTPException(status_code=402, detail="Daily budget exceeded")


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = (input_tokens / 1000 * PRICE_INPUT_PER_1K
            + output_tokens / 1000 * PRICE_OUTPUT_PER_1K)
    key = _today_key()
    pipe = r.pipeline()  # MULTI/EXEC: cộng tiền và đặt TTL đi cùng nhau
    pipe.incrbyfloat(key, cost)
    pipe.expire(key, KEY_TTL_SECONDS)
    pipe.execute()
    return cost
