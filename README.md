# Writer–Reviewer–Refiner Multi-Agent (minimal reference implementation)

Pipeline **3 agent** cho một bài hướng dẫn ngắn, **giới hạn đúng một vòng review**:

```
TutorialRequest (chủ đề, đối tượng, giới hạn từ)
        │
        ▼
   ┌──────────┐
   │  Writer  │ ──► Draft (bản nháp, Markdown)
   └──────────┘
        │
        ▼
   ┌──────────┐      8 mục: R1–R4 kiểm bằng code, L1–L4 kiểm bằng LLM
   │ Reviewer │ ──► ReviewReport (checklist: đạt/chưa đạt + nhận xét)   ← chỉ 1 lần
   └──────────┘
        │
        ▼
   ┌──────────┐
   │ Refiner  │ ──► FinalTutorial (bản hoàn chỉnh, chỉ sửa các mục chưa đạt)
   └──────────┘
        │
        ▼
   post_check: chạy lại R1–R4 bằng code (không gọi LLM, không sửa thêm)
```

**Output của mỗi lần chạy** (`outputs/<slug>/`):

| File | Nội dung |
|---|---|
| `01_draft.md` | Bản nháp do Writer viết |
| `02_review_checklist.md` / `.json` | Checklist đánh giá do Reviewer lập (bảng đọc được + dữ liệu máy đọc được) |
| `03_final.md` | Bản hoàn chỉnh do Refiner sửa |
| `trace.json` | Toàn bộ `PipelineResult` |

## Vai trò và ràng buộc

| Agent | Nhận | Trả về | Ràng buộc (ở cấp code) |
|---|---|---|---|
| **Writer** | `TutorialRequest` | `Draft` | Không thấy checklist — chỉ nhận brief (chủ đề, đối tượng, giới hạn từ) nên bản nháp là lần viết thật để Reviewer kiểm độc lập. |
| **Reviewer** | `Draft` | `ReviewReport` | `ReviewReport` **không có trường nào chứa văn bản đã sửa** → Reviewer chỉ đánh giá, không thể âm thầm sửa bài. |
| **Refiner** | `Draft`, `ReviewReport` | `FinalTutorial` | Không có tham chiếu tới Reviewer nên không thể mở vòng review thứ hai; chỉ thấy các mục **chưa đạt**; nếu mọi mục đạt thì trả nguyên bản nháp **mà không gọi LLM**. |

- `pipeline.py` không có vòng lặp: `ReviewerAgent.run` được gọi đúng 1 lần (`MAX_REVIEW_ROUNDS = 1`).
- Tính chất này được test ở `tests/test_pipeline.py` (đếm số lần gọi Reviewer, kể cả khi Refiner trả kết quả vẫn sai) và `tests/test_refiner.py` (signature, prompt chỉ chứa mục chưa đạt).

## Checklist (8 mục)

Chia theo **ai kiểm tra đáng tin cậy hơn**: LLM kém đếm từ/đếm bước, còn regex thì không đánh giá được "một bước một hành động".

| ID | Loại | Tiêu chí |
|---|---|---|
| R1 | code | Có tiêu đề cấp 1 (`# ...`) |
| R2 | code | Đủ 5 mục `##`: Mục tiêu, Chuẩn bị, Các bước, Kiểm tra kết quả, Lỗi thường gặp |
| R3 | code | Mục "Các bước" là danh sách đánh số 3–8 bước |
| R4 | code | Không vượt giới hạn từ (không tính khối code) |
| L1 | LLM | Mỗi bước một hành động rõ ràng, thể mệnh lệnh |
| L2 | LLM | Lệnh/mã/giá trị cụ thể nằm trong định dạng code |
| L3 | LLM | Ngôn ngữ hợp đối tượng, thuật ngữ khó được giải thích |
| L4 | LLM | Bám sát chủ đề, ngắn gọn |

Định nghĩa nằm ở `app/checklist.py`; muốn đổi tiêu chí chỉ cần sửa file này.

**Fail-closed:** nếu LLM không trả JSON hợp lệ cho một mục L, mục đó được ghi là **chưa đạt** kèm nhận xét rõ ràng, không bị coi là đạt.

## Giới hạn cần biết

- Vì chỉ có **một** vòng review, các mục L1–L4 chỉ được LLM đánh giá trên **bản nháp**; sau khi Refiner sửa không có ai đánh giá lại chúng. `post_check` chỉ chạy lại R1–R4 (bằng code) để báo cáo trung thực những gì đo được. Nếu Refiner sửa chưa đạt, kết quả vẫn được trả về kèm cảnh báo, không có vòng thứ hai (đúng yêu cầu).
- Đếm từ là xấp xỉ (tách theo khoảng trắng, bỏ khối code).

## Tech stack

- Python 3.10+, FastAPI + Uvicorn, Pydantic v2, `openai` SDK trỏ tới **bất kỳ endpoint OpenAI-compatible nào** qua `LLM_BASE_URL`, pytest.
- Không có chế độ mock/offline trong `app/`: **bắt buộc** có `LLM_API_KEY`. Test dùng `tests/fakes.py::FakeLLMClient` (chỉ nằm trong `tests/`).

## Cấu trúc

```
writer-reviewer-refiner-agent/
├── app/
│   ├── config.py          # đọc .env
│   ├── llm_client.py      # OpenAICompatibleClient
│   ├── schemas.py         # TutorialRequest, Draft, ReviewReport, FinalTutorial, PipelineResult
│   ├── checklist.py       # 8 tiêu chí + các hàm kiểm tra R1–R4 bằng code
│   ├── pipeline.py        # Writer -> Reviewer (1 lần) -> Refiner -> post_check
│   ├── artifacts.py       # ghi 01_draft.md, 02_review_checklist.*, 03_final.md, trace.json
│   ├── main.py            # FastAPI: GET /health, POST /run
│   └── agents/ writer.py, reviewer.py, refiner.py
├── tests/                 # conftest, fakes, test_checklist/writer/reviewer/refiner/pipeline/artifacts
├── e2e_runner.py          # MỘT LỆNH để chạy E2E
├── requirements.txt, pyproject.toml, .env.example, .gitignore
└── README.md
```

## Setup (local, VS Code)

```bash
cd writer-reviewer-refiner-agent
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # điền LLM_API_KEY (bắt buộc)
```

## Chạy test (offline, không cần API key)

```bash
pytest -v
```

## Chạy E2E

```bash
python e2e_runner.py                                   # 3 chủ đề demo
python e2e_runner.py --topic "Cài đặt Git trên Windows" --max-words 300
```

In ra bản nháp, checklist và bản hoàn chỉnh; lưu file vào `outputs/<slug>/`. Thoát với mã 1 nếu bản cuối vẫn trượt một mục R1–R4.

## Chạy như API (tuỳ chọn)

```bash
uvicorn app.main:app --reload --port 8000
```

`POST /run` với `{"topic": "...", "audience": "người mới bắt đầu", "max_words": 350}` → trả `PipelineResult` (draft, review, final, post_check). Swagger tại `/docs`.
