# Deployment Information

## Public URL
https://agent-production-db5e1c94.up.railway.app

## Platform
Railway — service `agent` (build từ `06-lab-complete/Dockerfile`) và service `Redis`, region `sfo`, 1 replica. Deploy ngày 26/11/2026 bằng `railway up` trong `06-lab-complete/`.

## Test Commands

Đặt biến trước khi chạy (key lấy trên Railway, không ghi vào repo):

```bash
BASE=https://agent-production-db5e1c94.up.railway.app
AGENT_API_KEY=<key đặt trên Railway>
```

### 4 lệnh tự kiểm (CP6)

```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```

Kết quả ngày 26/11/2026: `200`, `200`, `401`, `200`.

### API Test (with authentication)

```bash
curl -X POST "$BASE/ask" -H "X-API-Key: $AGENT_API_KEY" -H "Content-Type: application/json" \
  -d '{"question": "What is deployment?"}'
# {"question":"What is deployment?","answer":"Deployment là quá trình đưa code từ máy bạn lên server để người khác dùng được."}
```

### Các kiểm tra thêm trên URL public

| Kiểm tra | Kết quả |
|---|---|
| Sai key | 401 |
| Thiếu `question` | 422 |
| Gọi liên tiếp quá 10 request trong 1 phút | 429, header `Retry-After: 52` |
| `python check_production_ready.py --public-url $BASE` | `PASS 12/12` (42/42 checks) |

## Environment Variables Set

Đặt trên Railway cho service `agent`:

| Biến | Giá trị |
|---|---|
| `AGENT_API_KEY` | chuỗi ngẫu nhiên 43 ký tự (secret, chỉ nằm trên Railway) |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` (tham chiếu tới service Redis qua mạng nội bộ) |
| `ENVIRONMENT` | `production` |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` | `1.0` |
| `PORT` | do Railway tự cấp (app đang nghe cổng 8080) |

## Cấu hình service

Railway cảnh báo kiểu cấu hình bằng file (`railway.toml`) đã deprecated. Sau lần deploy đầu, health check của service vẫn để trống dù file có khai báo, nên các giá trị trong `railway.toml` (`healthcheckPath = "/health"`, timeout 30 giây, restart `ON_FAILURE` tối đa 3 lần) được đặt thẳng lên service rồi deploy lại.

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
