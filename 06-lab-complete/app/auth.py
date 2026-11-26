"""
API Key authentication (tiêu chí 6).

  • Client gửi header  X-API-Key: <key>
  • Key phải trùng biến môi trường AGENT_API_KEY
  • Thiếu hoặc sai key → HTTP 401
"""
import secrets

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import settings

# auto_error=False: thiếu header thì tự trả 401, không để FastAPI quyết định mã lỗi
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """Dependency cho FastAPI — dùng trong /ask: Depends(verify_api_key)."""
    expected = settings.agent_api_key
    # compare_digest so sánh trong thời gian không đổi → không dò được key qua độ trễ
    if (not api_key or not expected
            or not secrets.compare_digest(api_key.encode(), expected.encode())):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
    return api_key
