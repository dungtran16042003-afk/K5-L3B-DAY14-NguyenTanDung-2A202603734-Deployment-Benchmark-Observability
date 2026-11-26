"""
Rate limiting (tiêu chí 7) — sliding window 60 giây bằng Redis sorted set.

  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây
  • Vượt giới hạn → HTTP 429 kèm header Retry-After
  • State nằm trong Redis: mọi worker / instance dùng chung, còn nguyên sau restart
"""
import hashlib
import uuid

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60

# Lua chạy nguyên khối trong Redis: "đếm rồi ghi" không bị worker khác chen giữa.
# Dùng đồng hồ của Redis để các instance lệch giờ nhau vẫn tính đúng.
# Trả về 0 nếu được phép, hoặc số giây phải chờ nếu đã vượt giới hạn.
_SLIDING_WINDOW = r.register_script("""
local key    = KEYS[1]
local window = tonumber(ARGV[1])
local limit  = tonumber(ARGV[2])
local t      = redis.call('TIME')
local now    = tonumber(t[1]) + tonumber(t[2]) / 1000000

redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
if redis.call('ZCARD', key) >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  if not oldest[2] then return window end
  return math.max(1, math.ceil(tonumber(oldest[2]) + window - now))
end
redis.call('ZADD', key, now, ARGV[3])
redis.call('EXPIRE', key, window)
return 0
""")


def check_rate_limit(key: str) -> None:
    # Không lưu API key thô trong Redis, chỉ lưu bản băm
    bucket = "ratelimit:" + hashlib.sha256(key.encode()).hexdigest()[:16]
    retry_after = _SLIDING_WINDOW(
        keys=[bucket],
        args=[WINDOW_SECONDS, settings.rate_limit_per_minute, uuid.uuid4().hex],
    )
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} requests per minute",
            headers={"Retry-After": str(retry_after)},
        )
