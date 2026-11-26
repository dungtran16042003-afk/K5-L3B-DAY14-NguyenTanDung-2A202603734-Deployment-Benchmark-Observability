# Benchmark & Observability Report — Day 14

**Họ tên:** Nguyễn Tấn Dũng
**Ngày chạy:** 26/11/2026 (mục 1–3). Mục 4–6: chưa chạy
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
| Avg tokens / câu | 56.7 | 109.3 | 115.8 |
| Tổng cost (USD) | 0.000399 | 0.000764 | 0.000809 |
| Cost / câu đúng (USD) | 0.00039915 | 0.00003639 | 0.00003517 |
| Latency p50 / p95 (ms) | 151.8 / 183.2 | 198.7 / 221.4 | 198.4 / 214.0 |
| Quality gate | FAIL (≥ 80%) | PASS (≥ 80%) | PASS (≥ 100%, không regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| security-02 | `token`, `hết hạn`, `chữ ký` | Thêm tài liệu so sánh JWT với API key vào `KNOWLEDGE_BASE`, từ khoá kích hoạt `jwt` |
| scaling-03 | `cpu`, `memory`, `custom metrics` | Thêm tài liệu về Kubernetes HPA, từ khoá kích hoạt `hpa`, `kubernetes`, `autoscal` |

Cả hai câu sai vì retrieval không tìm được tài liệu nào nên agent trả câu chung chung. Không sửa `golden_dataset.jsonl`.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

v2 dùng khoảng 1,9 lần token mỗi câu (109,3 so với 56,7) và chậm hơn (p50 198,7 ms so với 151,8 ms) vì thêm bước retrieval và prompt dài hơn. Đổi lại accuracy tăng từ 4,3% lên 91,3%, nên **chi phí trên mỗi câu đúng rẻ hơn khoảng 11 lần**. So theo "cost mỗi câu" thì v1 trông rẻ hơn, nhưng phần lớn tiền đó mua câu trả lời sai. Eval chỉ có 23 câu nên số latency ở bảng này chỉ để tham khảo, latency chính thức lấy từ load test.

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

> Chưa thực hiện (CP8).

### 4.1 Screenshot

- [ ] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals)
- [ ] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian)
- [ ] Một trace lỗi trong Jaeger (có event `exception`)
- [ ] Trang Alerts của Prometheus với ít nhất 2 alert đang **firing**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | | | |
| B | `MOCK_SLOW_RATE=0.3` | | | |
| C | `LLM_MODEL=mock-llm-large` | | | |
| D | `docker pause` 1 instance | | | |
| E | `AGENT_VERSION=v1` | | | |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

...

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: ...
- Tổng thời gian: ... ms
- Span chiếm nhiều thời gian nhất: ... (... ms, ...%)
- Dòng log tương ứng (grep theo `trace_id`):

```json

```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | | | | | |
| 3 | | | | | |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

...

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. ...
  2. ...
  3. ...
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

...
