"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

from_url chỉ tạo connection pool, chưa mở kết nối → app khởi động được
kể cả khi Redis chưa sẵn sàng. Timeout ngắn để request không treo khi Redis chết.
"""
import redis

from app.config import settings

r = redis.Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)


def redis_healthy() -> bool:
    """Dùng cho GET /ready."""
    try:
        return bool(r.ping())
    except redis.RedisError:
        return False
