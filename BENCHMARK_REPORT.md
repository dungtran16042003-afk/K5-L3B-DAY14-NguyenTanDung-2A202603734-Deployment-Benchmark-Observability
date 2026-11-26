# Benchmark & Observability Report — Day 14

**Họ tên:** Nguyễn Tấn Dũng
**Ngày chạy:** 26/11/2026
**Môi trường:** Intel Core i7-13650HX (20 CPU logic), Windows 11 Home, WSL2 Ubuntu 24.04.5 (7,6 GiB RAM cấp cho WSL), Python 3.12.3, Docker 29.9.3 (Docker Desktop)

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Khi không có request chậm bất thường, p95 đo được khoảng 214 ms. Ngưỡng 500 ms chừa hơn 2 lần cho dao động, nhưng vẫn phát hiện được khi hơn 5% request rơi vào nhóm chậm ~1,7 s |
| Error rate `/ask` | < 2 % | Mock LLM mặc định lỗi 1% (`MOCK_ERROR_RATE=0.01`). Gấp đôi mức nền để không báo động vì dao động ngẫu nhiên |
| Accuracy trên golden dataset | ≥ 90 % | Bản v2 ban đầu đạt 91,3%. Đặt 90% để không chấp nhận bản mới kém hơn mức đó, kèm điều kiện không có regression |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

300 request mỗi mức, `MOCK_SLOW_RATE=0.03` (mặc định).

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.14 | 188.2 | 222.1 | 1703.8 | 0.67% | PASS |
| 10 | 38.67 | 186.6 | 217.7 | 1694.1 | 0.67% | PASS |
| 50 | 111.29 | 192.1 | 233.2 | 1690.6 | 0.33% | PASS |
| 100 | 85.64 | 259.9 | 1757.2 | 1892.6 | 1.00% | FAIL (p95) |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

Không. Từ 1 lên 10, RPS tăng 9,3 lần (gần tuyến tính). Từ 10 lên 50 (gấp 5) chỉ tăng 2,9 lần, còn ở 100 thì **giảm** xuống 85,64.

- Theo công thức RPS ≈ concurrency / latency trung bình, mức lý thuyết là 4,1 → 44 → 222 → 162. Đo được 4,14 → 38,67 → 111,29 → 85,64, càng nhiều song song càng hụt.
- Một phần do mẫu ít: chỉ có 300 request nên ở concurrency 50 cả bài chạy vài giây, vài request chậm ~1,7 s ở cuối kéo dài tổng thời gian trong khi các worker khác đã hết việc.
- Ở 100, p95 phía client lên 1757 ms. Đo lại 3 lần và so với log server (`reports/diag_client_vs_server.txt`): p95 phía server luôn khoảng 215–221 ms, còn p95 phía client ở c=100 lần lượt là 356, 274 và 1765 ms. Vậy phần chậm thêm nằm **ngoài** đoạn xử lý mà server đo được (phía client, kết nối hoặc chờ trước khi vào handler) và không ổn định giữa các lần. Tôi chưa xác định được nguyên nhân chính xác.

### 2.2 Tail latency

300 request, concurrency 20.

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 186.4 | 213.9 | 222.8 |
| 0.03 (mặc định) | 247.7 | 222.1 | 1698.1 |
| 0.1 | 314.2 | 1692.0 | 1710.7 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

p99 nhạy nhất: chỉ 3% request chậm đã làm p99 tăng từ 223 ms lên 1698 ms (7,6 lần), trong khi p95 gần như không đổi và avg chỉ thêm khoảng 61 ms. Khi tỉ lệ chậm là 10% (vượt 5%), p95 cũng nhảy lên 1692 ms. Avg lúc đó là 314 ms, vẫn "đạt" ngưỡng 500 ms dù cứ khoảng 10 người thì có 1 người chờ gần 1,7 s. Average trộn người nhanh với người chậm nên che mất nhóm bị chậm; percentile nói rõ bao nhiêu phần trăm người dùng chịu mức chờ nào.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100% (23/23) |
| Avg tokens / câu | 57.6 | 108.7 | 115.8 |
| Tổng cost (USD) | 0.000411 | 0.000756 | 0.000809 |
| Cost / câu đúng (USD) | 0.00041115 | 0.00003599 | 0.00003517 |
| Latency p50 / p95 (ms) | 163.1 / 189.1 | 181.6 / 215.1 | 179.1 / 216.7 |
| Quality gate | FAIL (≥ 80%) | PASS (≥ 80%) | PASS (≥ 100%, không regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| security-02 | `token`, `hết hạn`, `chữ ký` | Thêm tài liệu so sánh JWT với API key vào `KNOWLEDGE_BASE`, từ khoá kích hoạt `jwt` |
| scaling-03 | `cpu`, `memory`, `custom metrics` | Thêm tài liệu về Kubernetes HPA, từ khoá kích hoạt `hpa`, `kubernetes`, `autoscal` |

Cả hai câu sai vì retrieval không tìm được tài liệu nào nên agent trả câu chung chung. Không sửa `golden_dataset.jsonl`.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

v2 dùng khoảng 1,9 lần token mỗi câu (108,7 so với 57,6) và chậm hơn (p50 181,6 ms so với 163,1 ms) vì thêm bước retrieval và prompt dài hơn. Đổi lại accuracy tăng từ 4,3% lên 91,3%, nên **chi phí trên mỗi câu đúng rẻ hơn khoảng 11 lần**. So theo "cost mỗi câu" thì v1 trông rẻ hơn, nhưng phần lớn tiền đó mua câu trả lời sai. Eval chỉ có 23 câu nên số latency ở bảng này chỉ để tham khảo, latency chính thức lấy từ load test.

### Quality gate trong CI

`run_eval.py` trả **exit code 1** khi accuracy thấp hơn `--min-accuracy` hoặc có câu bị regression so với `--baseline`. Đã thử: chạy v1 với `--baseline reports/eval_v2.json` thì có 20 câu regression, gate FAIL, exit code 1. Chạy v2 đã sửa thì exit code 0.

Job GitHub Actions dưới đây dùng đúng cơ chế đó (chưa chạy trên GitHub). Bật branch protection yêu cầu check `eval` phải xanh thì pull request có eval fail sẽ không merge được.

```yaml
# .github/workflows/eval.yml
name: quality-gate
on: pull_request
jobs:
  eval:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: 06-lab-complete/benchmark-observability/develop
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - name: Chạy agent v2 rồi eval
        run: |
          AGENT_VERSION=v2 MOCK_ERROR_RATE=0 python app.py > agent.log 2>&1 &
          for i in $(seq 1 30); do curl -sf http://localhost:8000/health && break; sleep 1; done
          python eval/run_eval.py --min-accuracy 0.85 --baseline reports/eval_v2_fixed.json
```

---

## 4. Observability stack (production)

Stack: Nginx → agent (2 instance, giới hạn 0,5 CPU / 256 MiB mỗi instance) → Jaeger; Prometheus v3.16.0, Grafana 13.2.4, Locust 2.47.0. Số liệu gốc nằm trong `benchmark-results/` (`exercise_7_4_prometheus.txt`, `exercise_7_5_traces.txt`, `exercise_7_6_alerts.txt`).

Dockerfile mẫu của phần này làm container `agent` crash với `No module named 'uvicorn'` (home của user là `/app` còn thư viện ở `/home/agent/.local`). Đã thêm `ENV PYTHONUSERBASE=/home/agent/.local`.

### 4.1 Screenshot

- [x] [Dashboard Grafana khi đang có tải](screenshots/grafana-dashboard.png)
- [x] [Một trace chậm trong Jaeger](screenshots/jaeger-slow-trace.png)
- [x] [Một trace lỗi trong Jaeger (có event `exception`)](screenshots/jaeger-error-trace.png)
- [x] [Trang Alerts của Prometheus, 2 alert cùng **firing**](screenshots/prometheus-alert-firing.png)

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` (30 users) | `AgentHighErrorRate` | 91 s | Error rate: 0,83% → 18,2% |
| B | thêm `MOCK_SLOW_RATE=0.3` khi A vẫn bật (30 users) | `AgentHighLatencyP95` (cùng firing với A) | 154 s | Latency: p95 0,29 s → 1,89 s, avg 0,20 s → 0,54 s |
| C | `LLM_MODEL=mock-llm-large` (10 users) | `LLMCostBurnRateHigh` | 173 s | Cost burn rate: 1,11 → 6,13 USD/giờ (cửa sổ 5 phút còn đang tăng); p95 0,30 s → 0,74 s |
| D | `docker pause` 1 instance (30 users) | `AgentInstanceDown` | 34 s (lần chạy trước: 45 s) | Instances up: 2 → 1; Error rate vẫn 0,74% |
| E | `AGENT_VERSION=v1` (10 users) | Không có, theo dõi 240 s | — | Retrieval hit ratio mất dữ liệu; tokens/s 703 → 343; bảng phiên bản chuyển sang v1 |

Thời gian được đo bằng script hỏi API `/api/v1/alerts` mỗi 3 giây. Số ở cột cuối lấy bằng truy vấn Prometheus tương ứng với panel.

**Ngưỡng cost quá thấp so với tải này:** với 30 users và model nhỏ, `LLMCostBurnRateHigh` đã firing khi chưa đổi gì (khoảng 2,34 USD/giờ, ngưỡng 2). Vì vậy thí nghiệm C chạy với 10 users và chỉ bắt đầu khi không còn alert nào.

**Thí nghiệm D, lỗi 504 không hiện trên metric của agent:** trong thời gian pause, Locust ghi 35 lỗi trên 1015 request, gồm 29 lỗi 504 và 6 lỗi 503. Prometheus không có series `status="504"` nào và error rate của agent vẫn khoảng mức nền. 504 do Nginx trả về khi chờ instance bị đóng băng quá `proxy_read_timeout` (10 s); agent không bao giờ xử lý xong request đó nên không đếm. Metric chỉ phản ánh những gì chính service nhìn thấy, cần giám sát thêm ở load balancer hoặc kiểm tra từ bên ngoài.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Bằng đo chất lượng, vì mọi metric hạ tầng lúc đó còn "đẹp hơn": error rate 0,61%, p95 giảm từ 0,30 s xuống 0,20 s, cost giảm. Chạy eval trên golden dataset vào chính stack đang là v1 cho accuracy 4,3% (1/23), 22 câu regression so với bản đã sửa, exit code 1. Trong production nên: chặn deploy bằng eval trong CI, chạy eval định kỳ trên hệ thống thật và cảnh báo khi accuracy giảm, thêm alert cho retrieval hit ratio, và thu phản hồi của người dùng.

### 4.3 Debug bằng trace

Trace chậm nhất (theo `llm_ms` trong log tại thời điểm chọn):

- `trace_id`: `709924714f8dffc6be5761e88fab16c9`
- Tổng thời gian: 1712.1 ms
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (1695.7 ms, 99,0%); `agent.retrieve_context` chỉ 14.8 ms. Chậm do lời gọi LLM, không phải do code của agent.
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-26T10:16:33.342436+00:00", "level": "INFO", "service": "observable-agent", "instance": "9f6115a34ff6", "event": "llm_call", "trace_id": "709924714f8dffc6be5761e88fab16c9", "span_id": "1c6a752d8b0cd1ae", "request_id": "1294d9f27fdd", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 83, "output_tokens": 44, "cost_usd": 3.9e-05, "llm_ms": 1695.6}
```

Trace lỗi `52d821e27e24f3042ee3db0c284e94d2` (109.0 ms): span `chat mock-llm-small` có event `exception`, `Upstream LLM error: 503 Service Unavailable (mock)`. Log tương ứng:

```json
{"ts": "2026-11-26T10:16:36.525811+00:00", "level": "INFO", "service": "observable-agent", "instance": "9f6115a34ff6", "event": "llm_error", "trace_id": "52d821e27e24f3042ee3db0c284e94d2", "span_id": "5d867171c232f2b3", "request_id": "77d808303432", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

### 4.4 Trả lời Exercise 7.4 (30 users, 2 instance)

1. **p95 và avg:** p50 173 ms, avg 233 ms, p95 293 ms, p99 1834 ms. Avg cao hơn p50 60 ms và p99 gấp khoảng 8 lần avg: phần lớn request nhanh, một nhóm nhỏ (dưới 5%) chậm khoảng 1,7 s kéo avg lên. Chỉ nhìn avg hoặc p95 thì không thấy nhóm này.
2. **Nginx chia tải:** có, 8,87 và 9,07 request/s trên hai instance (tổng 17,93).
3. **Vì sao input tokens/s lớn hơn output:** 1392 so với 735 token/s. Prompt gửi đi gồm system prompt, tài liệu retrieve được và câu hỏi, còn câu trả lời chỉ dài cỡ tài liệu. Trên panel Tokens/s hai vùng được xếp chồng nên đường phía trên là tổng.
4. **`curl http://localhost:8080/metrics`:** trả **404**, vì Nginx chặn đường này. Metric lộ thông tin nội bộ (route, lưu lượng, phiên bản); Prometheus lấy trực tiếp từ từng agent trong mạng nội bộ.

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số của dòng `POST /ask` trong `benchmark-results/scale_*_stats.csv`.

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 57.84 | 190 | 220 | 1700 | 84 / 7180 (1,17%) |
| 3 | 57.22 | 190 | 220 | 1700 | 65 / 7204 (0,90%) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

Không. RPS, p50, p95, p99 gần như y hệt. Với tải này instance không phải nút thắt:

- **Thời gian trả lời do LLM quyết định:** p50 190 ms, LLM p95 đo phía agent khoảng 198 ms ở cả hai lượt. Thêm instance không làm LLM nhanh hơn.
- **Agent còn dư sức:** giữa lượt 1 instance, CPU của agent là 13,6% trong giới hạn 50% (một lần đo `docker stats`).
- **Tải bị giới hạn bởi chính Locust:** mỗi user chờ trả lời rồi nghỉ 0,5–2 s. 100 users chỉ tạo được tối đa cỡ 100 / (1,25 + 0,2) ≈ 68 request/s; đo được 63,8 và 62,8 (tính cả `/health` và 10 s ramp-up). Muốn thấy lợi ích của scale phải tăng tải đến khi một instance chạm giới hạn CPU, phần này chưa thử.
- Toàn bộ lỗi là 503, tức lỗi LLM giả lập (`MOCK_ERROR_RATE=0.01`), không phải quá tải.

p95 của Locust (220 ms) thấp hơn p95 trên Prometheus (khoảng 293 ms) vì `histogram_quantile` nội suy trong bucket 200–300 ms, còn Locust đo từng request.

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. Phải nhìn percentile: 3% request chậm gần như không đổi p95 nhưng đẩy p99 từ 223 ms lên 1698 ms.
  2. Dashboard xanh không có nghĩa là trả lời đúng: đổi sang v1 không alert nào firing trong khi accuracy còn 4,3%.
  3. Thêm instance chỉ có ích khi instance là nút thắt: ở đây 1 và 3 instance cho cùng RPS và p95.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

Alert 5xx/504 đo tại load balancer và kiểm tra từ bên ngoài (vì thí nghiệm D); alert chất lượng từ eval định kỳ và retrieval hit ratio (vì thí nghiệm E); alert p99; đổi ngưỡng cost sang chi phí trên mỗi request hoặc theo ngân sách ngày để không báo động chỉ vì lưu lượng tăng.
