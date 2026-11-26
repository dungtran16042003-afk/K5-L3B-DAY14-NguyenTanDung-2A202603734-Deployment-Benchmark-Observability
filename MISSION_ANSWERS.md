# Day 14 Lab - Mission Answers

> Output bên dưới chạy trong WSL2 (Ubuntu 24.04) ngày 26/11/2026, đã rút gọn header không liên quan. Token JWT đã che.

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

File `01-localhost-vs-production/develop/app.py`:

1. **Dòng 17–18, secret ghi thẳng trong code** (`OPENAI_API_KEY`, `DATABASE_URL` có mật khẩu). Push lên repo là lộ, xoá đi vẫn còn trong lịch sử git; muốn đổi key phải sửa code và deploy lại.
2. **Dòng 21–22, cấu hình cố định** (`DEBUG = True`, `MAX_TOKENS`). Không đổi được theo môi trường nếu không sửa code, dễ đem chế độ debug lên production.
3. **Dòng 33–38, log bằng `print` và in cả API key** (dòng 34). Ai xem được log là có key; log không có level, thời gian hay cấu trúc nên khó lọc.
4. **Không có `/health`** (dòng 42–43). Gọi `GET /health` ra 404, nền tảng không có cách biết process bị treo để khởi động lại.
5. **Dòng 51–52, `host="localhost"` và `port=8000` cố định.** App chỉ nghe ở `127.0.0.1` nên đặt trong container thì bên ngoài không gọi vào được; cổng do nền tảng cấp qua biến `PORT` bị bỏ qua.
6. **Dòng 53, `reload=True`.** Chạy thêm một process theo dõi file, tốn tài nguyên và có thể tự restart giữa chừng trên production.
7. **Dòng 30–31, `/ask` không xác thực, không giới hạn độ dài input, nhận câu hỏi qua query string.** Ai cũng gọi được, và nội dung câu hỏi nằm trong access log.

### Exercise 1.2: Chạy bản develop

```text
$ curl -i -X POST "http://localhost:8000/ask?question=Hello"
HTTP/1.1 200 OK
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}

$ curl -i http://localhost:8000/health
HTTP/1.1 404 Not Found
{"detail":"Not Found"}

$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 422 Unprocessable Entity
{"detail":[{"type":"missing","loc":["query","question"],"msg":"Field required","input":null}]}

$ ss -ltn | grep :8000
LISTEN 0  2048  127.0.0.1:8000  0.0.0.0:*

--- log của server
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this      <- secret bị in ra (key giả của đề)
INFO:     127.0.0.1:56018 - "POST /ask?question=Hello HTTP/1.1" 200 OK
```

Bản develop nhận `question` qua query string nên gửi JSON bị 422.

### Exercise 1.3: Comparison table

| Feature           | Develop                        | Production                                                                                   | Why Important?                                                                  |
| ----------------- | ------------------------------ | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| Config            | Hằng số trong code           | `config.py` đọc biến môi trường, dừng ngay nếu production thiếu `AGENT_API_KEY` | Cùng một code chạy được ở dev/staging/prod, secret không vào git       |
| Health check      | Không có (404)               | `/health` (liveness) và `/ready` (readiness)                                            | Nền tảng biết khi nào restart, khi nào được chuyển traffic vào        |
| Logging           | `print`, lộ API key         | `logging` dạng JSON, chỉ ghi độ dài câu hỏi                                         | Lọc và phân tích được, không lộ dữ liệu nhạy cảm                   |
| Shutdown          | Không xử lý gì thêm       | `lifespan` và handler SIGTERM                                                             | Đóng kết nối, hạ readiness, không cắt ngang request khi deploy bản mới |
| Địa chỉ, cổng | `127.0.0.1:8000` cố định  | `0.0.0.0` và `PORT` từ env                                                             | Chạy được trong container và trên cloud                                   |
| Input             | Query string, không kiểm tra | JSON body, rỗng thì 422                                                                    | Báo lỗi rõ ràng, câu hỏi không nằm trên URL                            |

Ví dụ anti-pattern đã được sửa: `develop/app.py:51` dùng `host="localhost"`, còn `production/app.py` dùng `host=settings.host` (mặc định `0.0.0.0`). Chạy thật thấy `0.0.0.0:8000` và `GET /health`, `GET /ready` đều trả 200.

**Hai điểm bản "production" mẫu vẫn chưa ổn (phát hiện khi chạy):**

- Chạy mặc định (không có `OPENAI_API_KEY`) thì **không thấy dòng log JSON nào**. `config.py` gọi `logging.warning` ngay lúc import, trước `logging.basicConfig` trong `app.py`, nên cấu hình log của `app.py` không còn tác dụng và mức INFO bị bỏ. Đặt một key giả thì log hiện ra.
- Khi log hiện ra, **3/8 dòng JSON không parse được** vì chuỗi JSON bị nhét vào trong trường `"msg"` mà không escape. Nên dùng formatter gọi `json.dumps`.

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

1. **Base image:** `python:3.11` (bản đầy đủ của Debian kèm Python).
2. **Working directory:** `/app`.
3. **Vì sao COPY requirements.txt trước:** Docker cache theo từng lớp. Khi chỉ sửa code, lớp cài dependencies được dùng lại; chỉ khi `requirements.txt` đổi mới `pip install` lại, build nhanh hơn nhiều.
4. **CMD vs ENTRYPOINT:** `CMD` là lệnh mặc định, bị thay thế khi truyền lệnh khác vào `docker run` (ví dụ `docker run my-agent:develop id -un`). `ENTRYPOINT` là chương trình cố định của container, tham số của `docker run` được nối vào sau nó, muốn thay phải dùng `--entrypoint`.

### Exercise 2.2: Build và run

```text
$ docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
$ docker run -p 8000:8000 my-agent:develop

$ curl -i -X POST "http://localhost:8000/ask?question=What%20is%20Docker"
HTTP/1.1 200 OK
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}

$ curl http://localhost:8000/health
{"status":"ok","uptime_seconds":0.9,"container":true}
```

### Exercise 2.3: Image size comparison

```text
$ docker images my-agent
IMAGE               ID             DISK USAGE   CONTENT SIZE
my-agent:advanced   2fbc9eb362d8        240MB         57.4MB
my-agent:develop    d9af583897cc       1.67GB          426MB
```

- Develop: **1670 MB**
- Production: **240 MB**
- Difference: **giảm khoảng 85,6%** (theo `DISK USAGE`; theo kích thước nén là khoảng 86,5%)
- **Stage 1 (builder):** từ `python:3.11-slim`, cài `gcc`, `libpq-dev`, rồi `pip install --user` vào `/root/.local`.
- **Stage 2 (runtime):** bắt đầu lại từ `python:3.11-slim`, chỉ copy thư viện đã cài và code, chạy bằng user `appuser`.
- **Vì sao nhỏ hơn:** phần giảm lớn đến từ base `slim` thay cho bản đầy đủ; multi-stage giữ compiler và file tạm lại ở builder. Kiểm tra trong container: bản develop có `/usr/bin/gcc` và chạy bằng `root`, bản advanced không có `gcc` và chạy bằng `appuser`.

### Exercise 2.4: Docker Compose stack

```text
Client ──:80──▶ nginx ──▶ agent:8000 ──┬──▶ redis:6379
                (mạng internal)        └──▶ qdrant:6333
```

Chỉ Nginx mở cổng ra máy host. Các service gọi nhau bằng tên service qua mạng `internal`.

```text
$ docker compose -p k5-day14-docker up -d --build
SERVICE   STATUS         PORTS
agent     Up (healthy)   8000/tcp
nginx     Up             0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
qdrant    Up (healthy)   6333-6334/tcp
redis     Up (healthy)   6379/tcp

$ curl -i http://localhost/health
HTTP/1.1 200 OK
Server: nginx
{"status":"ok","uptime_seconds":5.6,"version":"2.0.0","timestamp":"2026-11-26T08:40:36.742139"}

$ curl -i -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question": "Explain microservices"}'
HTTP/1.1 200 OK
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}

# 40 request đồng thời
     21 200
     19 429        <- rate limit 10 req/s, burst 20 của Nginx

# từ trong container agent
agent -> redis 6379 OK
agent -> qdrant 6333 OK
$ curl http://localhost:8000/health   -> không kết nối được (agent không mở cổng ra host)
```

Nhận xét: chú thích trong file ghi agent có 2 replicas nhưng thực tế chạy 1. `main.py` chưa dùng Redis hay Qdrant, hai service này mới chỉ kết nối được qua mạng.

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deployment

- Nền tảng: **Railway** (Exercise 3.1), gồm service agent và Redis
- URL: https://agent-production-db5e1c94.up.railway.app
- Screenshot: [dashboard](screenshots/dashboard.png), [running](screenshots/running.png), [test](screenshots/test.png)
- 4 lệnh tự kiểm ở CP6 trả về `200`, `200`, `401`, `200`. Chi tiết trong [DEPLOYMENT.md](DEPLOYMENT.md).

Hai điều gặp khi deploy:

- Railway cấp `PORT=8080`, nên domain phải trỏ vào cổng 8080. App chạy được vì `CMD` đọc biến `PORT`.
- Health check trong `railway.toml` không được áp vào service (Railway báo kiểu cấu hình này đã deprecated), nên đặt `/health` thẳng trên service rồi deploy lại.

### So sánh `railway.toml` và `render.yaml`

So `06-lab-complete/railway.toml` với `03-cloud-deployment/render/render.yaml`.

| Điểm                      | `railway.toml`                                        | `render.yaml`                                                                         | Vì sao khác                                                                                                    |
| --------------------------- | ------------------------------------------------------- | --------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Phạm vi                    | Cách build và deploy **một** service           | Blueprint khai báo **nhiều** service (web và Redis)                            | Render mô tả cả hạ tầng trong file; Railway tạo thêm Redis trên dashboard hoặc CLI                      |
| Cách build                 | `builder = "DOCKERFILE"`                              | Bản mẫu dùng `runtime: python` với `buildCommand`, `startCommand`             | Mình dùng Dockerfile nên lệnh chạy nằm trong `CMD`; bản mẫu để Render tự dựng môi trường Python |
| Health check                | `healthcheckPath = "/health"`                         | `healthCheckPath: /health`                                                            | Cùng ý nghĩa, khác tên khoá                                                                                |
| Biến môi trường, secret | Không nằm trong file, đặt trên Railway             | Khai báo trong `envVars`, secret dùng `sync: false` hoặc `generateValue: true` | Cả hai đều không ghi giá trị secret vào git                                                               |
| Restart, region, plan       | Có `restartPolicyType`; file không ghi region, plan | Có `region`, `plan`, `autoDeploy`                                                | Mỗi nền tảng cho cấu hình qua file ở mức khác nhau                                                       |

### Exercise 3.3: Pipeline Cloud Run

1. `cloudbuild.yaml` chạy 4 bước nối tiếp bằng `waitFor`: **test** (cài dependencies, chạy `pytest`) → **build** image gắn tag `$COMMIT_SHA` và `latest`, tận dụng `--cache-from` → **push** lên `gcr.io` → **deploy** bằng `gcloud run deploy` tại `asia-southeast1`. Bước trước lỗi thì các bước sau không chạy.
2. Lúc deploy đặt 1–10 instance, 512 MiB, 1 CPU, và lấy `OPENAI_API_KEY` từ Secret Manager.
3. `service.yaml` mô tả service theo kiểu khai báo: scale 1–10, tối đa 80 request đồng thời mỗi instance, secret qua `secretKeyRef`, liveness gọi `/health`, startup probe gọi `/ready`.
4. Thư mục mẫu không có `tests/`, nên muốn pipeline chạy thật phải bổ sung test.

## Part 4: API Security

### Exercise 4.1-4.3: Test results

**4.1 API key (bản develop)** — `secret-key-123` là key mẫu của đề.

```text
$ curl -i ... (không có key)
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

$ curl -i ... -H "X-API-Key: wrong-key"
HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}

$ curl -i ... -H "X-API-Key: secret-key-123"
HTTP/1.1 200 OK
{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

- Key được kiểm tra ở dependency `verify_api_key`, gắn vào `/ask` bằng `Depends`.
- Thiếu key trả 401, sai key trả 403 (Part 6 yêu cầu cả hai là 401).
- Rotate key: đổi biến `AGENT_API_KEY` rồi khởi động lại. Muốn không gián đoạn thì cho phép tạm hai key (cũ và mới) trong thời gian chuyển đổi.

**4.2 JWT (bản production)** — `POST /auth/token` với tài khoản demo, server ký token HS256 chứa `sub`, `role`, `exp` (60 phút). Các request sau gửi `Authorization: Bearer`, server chỉ kiểm tra chữ ký và hạn, không cần tra database.

```text
$ curl -i -X POST http://localhost:8000/ask ... (không token)
HTTP/1.1 401 Unauthorized
{"detail":"Authentication required. Include: Authorization: Bearer <token>"}

$ curl -i ... -H "Authorization: Bearer not.a.token"
HTTP/1.1 403 Forbidden
{"detail":"Invalid token."}

$ curl -X POST http://localhost:8000/auth/token -d '{"username":"student","password":"demo123"}'
{"access_token": "<token đã che>", "token_type": "bearer", "expires_in_minutes": 60, "hint": "<đã che>"}

$ curl -i ... -H "Authorization: Bearer <token đã che>"
HTTP/1.1 200 OK
{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":9,"budget_remaining_usd":1.6e-05}}
```

**4.3 Rate limit**

```text
request 2 -> 200
...
request 10 -> 200
request 11 -> 429
request 12 -> 429
request 13 -> 429
request 14 -> 429
request 15 -> 429

$ curl -i ... (đã vượt giới hạn)
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
retry-after: 59
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

- Thuật toán: **sliding window** lưu timestamp từng request trong `deque` (chú thích ghi "counter" nhưng code là dạng log timestamp).
- Giới hạn: user 10 request/phút, admin 100 request/phút.
- Admin không bỏ qua hẳn giới hạn: `role == "admin"` thì dùng `rate_limiter_admin` rộng hơn. Đăng nhập `teacher` thấy `requests_remaining: 99`.
- Hạn chế: state nằm trong RAM, nhiều instance thì mỗi instance đếm riêng và mất khi restart.

### Exercise 4.4: Cost guard

**Cách bản mẫu làm:** trước khi gọi LLM, `check_budget` xem tổng chi phí cả hệ thống (10 USD/ngày, vượt thì 503) rồi tới từng user (1 USD/ngày, vượt thì 402), cảnh báo khi đạt 80%. Sau khi gọi, `record_usage` cộng token và tính tiền theo giá mỗi 1K token.

```text
$ GET /me/usage
{"user_id":"student","date":"2026-11-26","requests":10,"input_tokens":38,"output_tokens":292,"cost_usd":0.000181,"budget_usd":1.0,"budget_remaining_usd":0.999819,"budget_used_pct":0.0}
```

**Nhận xét:**

- Trường `budget_remaining_usd` trong response của `/ask` thực ra trả **số đã dùng** (`usage.total_cost_usd`); `/me/usage` mới tính đúng số còn lại.
- Chi phí lưu trong RAM nên restart là mất. Bản production nên lưu Redis, ví dụ key `budget:{user}:{YYYY-MM}`, cộng bằng `INCRBYFLOAT` và đặt TTL.
- Ở Part 6 mình lưu tổng chi phí theo ngày trong Redis (`cost:YYYY-MM-DD`). Kiểm tra trước, ghi sau nên request song song có thể vượt ngân sách một ít.
- Rate limit chặn **tốc độ** gọi, cost guard chặn **tổng tiền**. Gọi chậm nhưng câu rất dài vẫn tốn tiền, nên cần cả hai.

## Part 5: Scaling & Reliability

### Exercise 5.1-5.5: Implementation notes

**5.1 Health và readiness**

```text
$ curl -i http://localhost:8000/health
HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":0.7,"version":"1.0.0","environment":"development", ... "checks":{"memory":{"status":"ok","used_percent":14.0}}}

$ curl -i http://localhost:8000/ready
HTTP/1.1 200 OK
{"ready":true,"in_flight_requests":1}
```

`/health` (liveness) trả lời "process còn sống không", fail thì nền tảng restart. `/ready` (readiness) trả lời "nhận traffic được chưa", fail thì load balancer ngừng chuyển request vào nhưng không restart. Vì vậy mất Redis thì `/ready` nên 503 còn `/health` vẫn 200: restart app không làm Redis sống lại.

**5.2 Graceful shutdown** — mock của bài này delay 3 giây; gửi SIGTERM sau 0,05 giây.

```text
in-flight request -> HTTP 200 sau 3.100202s
server exit code: 0
request mới sau khi tắt: không kết nối được

INFO:     Shutting down
INFO:     127.0.0.1:52096 - "POST /ask?question=Long%20task HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
... INFO 🔄 Graceful shutdown initiated...
... INFO ✅ Shutdown complete
... INFO Received signal 15 — uvicorn will handle graceful shutdown
```

Request đang chạy vẫn xong rồi server mới tắt. uvicorn tự chờ request trước khi chạy phần shutdown của `lifespan`; dòng log của handler tự viết xuất hiện cuối cùng.

**5.3 Stateless** — Nếu lưu lịch sử trong dict ở RAM, request sau có thể vào instance khác và không thấy lịch sử; instance restart là mất. Bản production lưu `session:{id}` trong Redis (TTL 3600 giây, tối đa 20 message). Hai điểm cần lưu ý: nếu lúc khởi động không nối được Redis, app **lặng lẽ chuyển sang RAM**; và `append_to_history` đọc rồi ghi nên hai request cùng session chạy song song có thể ghi đè nhau.

**5.4 Load balancing**

```text
$ docker compose -p k5-day14-scaling up -d --build --scale agent=3
k5-day14-scaling-agent-1   Up (healthy)
k5-day14-scaling-agent-2   Up (healthy)
k5-day14-scaling-agent-3   Up (healthy)
k5-day14-scaling-nginx-1   Up            0.0.0.0:8080->80/tcp
k5-day14-scaling-redis-1   Up (healthy)
```

Số request `/chat` trong log sau `test_stateless.py`: agent-1: 2, agent-2: 2, agent-3: 1.

**5.5 Test stateless**

```text
$ python test_stateless.py
Request 1: [instance-4f39b8]
Request 2: [instance-7913ed]
Request 3: [instance-943531]
Request 4: [instance-4f39b8]
Request 5: [instance-7913ed]
Instances used: {'instance-943531', 'instance-7913ed', 'instance-4f39b8'}
✅ All requests served despite different instances!
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

Giải thích: 5 câu cùng một session đi qua 3 instance khác nhau mà lịch sử đủ 10 message, vì state nằm trong Redis chứ không nằm trong instance.

Script không tắt instance nào, nên thử thêm: dừng agent-1 giữa cuộc hội thoại (client timeout 15 giây).

```text
turn 1..3 -> 200 (3 instance khác nhau)
docker stop /k5-day14-scaling-agent-1
turn 4 -> LỖI timed out
turn 5 -> 200
turn 6 -> 200
turn 7 -> LỖI timed out
turn 8 -> 200
turn 9 -> 200
history count: 14 | câu hỏi còn lại: turn 1, 2, 3, 5, 6, 8, 9
```

Lịch sử không mất, nhưng **2/6 request sau đó bị timeout**, tức là chuyển đổi chưa trơn tru. Theo `nginx.conf`, nguyên nhân khả dĩ: Nginx chỉ phân giải tên `agent` lúc nạp cấu hình nên vẫn gửi tới IP đã tắt, và `proxy_connect_timeout` mặc định (60 giây) dài hơn timeout của client. Hướng sửa (chưa thử): đặt `proxy_connect_timeout` ngắn và dùng `server agent:8000 resolve` như `nginx.conf` của Part 7.

## Part 6: Output `check_production_ready.py`

Chạy đầy đủ trong WSL2 (`os.name = posix`) với Docker.

```text
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 41/41 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
```

### Tự kiểm tra xử lý lỗi (stack Compose)

| Trường hợp                                                             | Mã trả về             |
| ------------------------------------------------------------------------- | ------------------------ |
| Không key / sai key                                                      | 401                      |
| Thiếu `question`, rỗng, chỉ dấu cách, sai kiểu, dài 2001 ký tự | 422                      |
| JSON hỏng, body trống, body là mảng                                   | 422                      |
| Byte không phải UTF-8 trong body JSON                                   | 400                      |
| Sai method / URL không tồn tại                                         | 405 / 404                |
| Vượt 10 request/phút                                                   | 429, `Retry-After: 59` |
| Dừng Redis: `/health`, `/ready`, `/ask`                            | 200, 503, 503            |

Log của agent trong lần thử: 0 dòng `Traceback`, 0 lần xuất hiện API key. `docker compose stop` mất 0,7 giây, exit code 0.

## Part 7: Exercise 7.1 (đọc metrics)

1. **Counter:** `http_requests_total{method="POST",route="/ask",status="200"}`. **Gauge:** `agent_in_flight_requests`. **Histogram:** `http_request_duration_seconds` và metric mình thêm `agent_question_length_chars`.
2. Nếu dùng URL thật làm label `route`, mỗi URL lạ bot quét tạo một time series mới, số series tăng không giới hạn và Prometheus tốn RAM. Gọi thử `/wp-admin`, `/.env`, `/a1b2c3` thì cả 3 gom vào một series `route="unmatched"` với giá trị 3.

## AI log

AI dùng: Claude Code (chạy lệnh và sửa file trực tiếp trên máy). Ban đầu làm theo kiểu hướng dẫn từng bước, sau đó giao cho AI làm tiếp các phần chạy được trên máy.

| Phần                     | Mình hỏi gì                                     | Nhận được gì                                                                                                                                                              | Mình tự sửa và tự kiểm tra thế nào                                                                                                                                            |
| ------------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Chuẩn bị                | Cài Docker, tóm tắt yêu cầu và phạm vi bài | Cài WSL2 Ubuntu, Docker Desktop, môi trường Python; bảng nhiệm vụ theo CP                                                                                               | Tự đăng nhập Docker Desktop bằng tài khoản GitHub                                                                                                                              |
| Part 1, 2, 4, 5           | Làm tiếp các phần                              | AI chạy các ví dụ, lấy output và số đo, **soạn toàn bộ câu trả lời**                                                                                       | Đối chiếu số dòng anti-pattern; xem dung lượng image 1.67GB và 240MB; đọc code thấy giới hạn 10 request/phút                                                            |
| Part 3 (phần đọc file) | Làm tiếp các phần                              | AI soạn bảng so sánh cấu hình và mô tả pipeline Cloud Run                                                                                                              | So hai file cấu hình; đếm đúng 4 bước test, build, push, deploy                                                                                                               |
| Part 6                    | Làm tiếp các phần                              | AI **viết code** trong `app/`, `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.env.example`, `railway.toml`; chạy script chấm và thử lỗi        | Đọc code, hiểu khi nào trả 401, 429, 402                                                                                                                                         |
| Part 7 (7.1–7.3)         | Làm tiếp các phần                              | AI thêm metric, chạy load test và eval, sửa `KNOWLEDGE_BASE`, **soạn** `BENCHMARK_REPORT.md` mục 1–3                                                          | So p95 trong JSON với báo cáo; xem hai tài liệu thêm vào knowledge base                                                                                                        |
| Part 3, deploy            | Test lại, push và deploy                         | Mình đăng nhập Railway; AI tạo project và Redis, đặt biến môi trường, deploy, sửa cổng domain và health check, thêm trang gốc `/` vào app, kiểm tra URL, **soạn** `DEPLOYMENT.md` | Tự đăng nhập Railway bằng GitHub, tự chạy script và thấy 200, 200, 401, 200. Mở `/health` trên trình duyệt, báo lỗi khi mở trang để sửa, chụp 3 ảnh phần này |
| Part 7 (7.4–7.7) | Bật Grafana và làm tiếp | AI sửa Dockerfile mẫu, bật stack, tạo tải, chạy thí nghiệm cảnh báo và đo scale, chỉ đúng trace cần chụp, **soạn** `BENCHMARK_REPORT.md` mục 4–6 | *(tự điền)* |
