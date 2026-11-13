# Báo cáo cá nhân — Day 6

Nguyễn Thế Cường — MSSV 2A202603355 — lớp L3A.

## Dữ liệu và pipeline
- Chủ đề, nguồn/quyền, số trang và quy tắc tính trang: Sổ tay sinh viên 2024, Trường Đại học Mở TP.HCM, [nguồn PDF chính thức](https://ou.edu.vn/wp-content/uploads/2024/09/So-Tay-SV-2024.pdf). PDF có 167 trang vật lý; chọn trang 39–77 gồm 39 trang nội dung đã kiểm tra, 79.077 ký tự sau chuẩn hóa. Trang 68 chia thành hai mục nên có 40 đơn vị nguồn, không tính thành 40 trang. [Manifest](data/manifest.json) ghi danh sách trang, số ký tự và quy tắc tính. Đã tìm thấy điều khoản sử dụng cá nhân, không kinh doanh; chưa xác minh giấy phép mở hoặc quyền riêng cho embedding và phân phối lại. Căn cứ và giới hạn được lưu tại [LICENSE_REVIEW.md](data/LICENSE_REVIEW.md). PDF và artifacts chứa nội dung nguồn hiện giữ local.
- Chuẩn hóa, lỗi và giới hạn: dùng Python/pypdf, Unicode NFC, chuẩn hóa khoảng trắng trong dòng, giữ xuống dòng, bỏ header lặp theo mẫu chính xác. Giữ số trang vật lý từ 1 và tách section theo heading đã kiểm tra. Trang rỗng/lỗi được ghi log, không âm thầm dùng mock. Text còn lỗi khoảng trắng trong từ; bảng có thể mất bố cục. Chunk không vượt ranh giới trang/section nhưng có thể cắt giữa câu khi đoạn quá dài. A có 192 chunk, tổng 86.674 ký tự; B có 202 chunk, tổng 78.999 ký tự. Tổng ký tự A cao hơn vì overlap, không phải corpus lớn hơn. Chi tiết độ dài trong [chunk_stats.csv](results/chunk_stats.csv).
- Embedding model/provider/version/số chiều, vector store/version, metric, lệnh chạy và chi phí: model thật chạy local `intfloat/multilingual-e5-small`, revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`, Sentence Transformers 6.3.0, PyTorch 2.15.0, CPU, 384 chiều, chuẩn hóa L2, prefix `passage: ` cho tài liệu và `query: ` cho câu hỏi. Giới hạn 512 token; các chunk A/B đã kiểm tra tối đa 201/167 token ở lần đo, không vượt giới hạn. Adapter báo lỗi nếu quá dài. PostgreSQL 16.16 + pgvector 0.8.7, named volume, exact cosine search top-3, chưa dùng ANN. Không gọi API embedding trả phí; chi phí API embedding bằng 0, chưa tính điện/phần cứng. [Bằng chứng local](artifacts/local_model_verification.json) xác nhận một query mới chạy CPU thành công khi offline và chặn socket; các log corpus nằm trong `results/embedding_runs.json` và `results/reproduced/embedding_runs.json`. [Phiên bản thư viện](artifacts/package_versions.json), [cấu hình](artifacts/strategies.json).
- Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn: `document_id` (string, từ manifest), `source` (string, URL nguồn), `page` (integer, trang PDF vật lý). Trường filter `section` (string) lấy từ heading đã kiểm tra với ba giá trị `cong_tac_sinh_vien`, `quy_che_dao_tao`, `ngoai_ngu_khong_chuyen`. `unit_id`, `start_char`, `end_char` hỗ trợ truy vết vị trí trong text chuẩn hóa. Source/page giúp mở đúng bằng chứng; section giúp thu hẹp phạm vi nhưng không khôi phục evidence bị cắt. Xem [schema](artifacts/metadata_schema.json). Nạp lại thay toàn bộ chunk tài liệu trong từng A/B bằng transaction, không nhân đôi; [minh chứng](results/reingestion_check.md). Tài liệu bị loại hẳn khỏi corpus cần xử lý xóa riêng.

Lệnh tái lập chạy từ thư mục `starter/` sau khi có đúng PDF và benchmark được phép sử dụng:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose -p day6_student_starter up -d --wait
.\.venv\Scripts\python.exe scripts/check_setup.py
.\.venv\Scripts\python.exe -m src.run --stage all
.\.venv\Scripts\python.exe scripts/run_benchmark.py --split dev
.\.venv\Scripts\python.exe scripts/run_benchmark.py --split test
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_artifacts.ps1
```

PDF đặt tại `data/raw/So-Tay-SV-2024.pdf` ở root, hash SHA-256 `6d71ed975f4ac9b0da31fd7b6e0ae778d44ed89bfe7bc8d92e17e3ed8f5791a1`. Cần đúng `benchmark/questions.jsonl` đã chạy, không tự tạo bộ khác rồi so điểm cũ. Các file có nội dung nguồn đang bị loại khỏi Git; chưa có kênh bàn giao được xác nhận cho người chấm nên clone repo hiện chưa đủ tái lập độc lập. Không tuyên bố đã bàn giao hoặc đã được cấp phép. Stage pipeline ghi `results/reproduced/`; benchmark chạy lại mặc định ghi `results/reproduced/benchmark/`, giữ nguyên kết quả gốc. Test chỉ chạy sau khi cố định cấu hình; lần chạy lại chỉ kiểm chứng, không tinh chỉnh.

## Cấu hình và benchmark
- A / B / C (tham số cụ thể, khác biệt duy nhất B–C): A fixed-size 500 ký tự, overlap 50, không filter. B ghép theo đoạn tối đa 500 ký tự, đoạn quá dài chia thành cửa sổ cân bằng, không overlap/filter. C tái sử dụng chunk/vector B và chỉ thêm filter `section` khi câu hỏi cung cấp trước. Câu không filter thì C chạy như B. Giữ cùng corpus, model, metric/store và benchmark. A–B khác cả phương pháp chia và overlap; chỉ B–C cô lập đúng một yếu tố.
- ≥20 câu: phân chia ≥15 dev / ≥5 test, câu metadata filter và cách kiểm chứng evidence: 20 câu, q01–q15 dev, q16–q20 test; 5 câu filter gồm q01/q03/q06 dev và q16/q18 test. Mỗi câu có đáp án, nguồn, trang và evidence; tất cả evidence được kiểm tra tồn tại trong text nguồn trước retrieval. Có câu trực tiếp, diễn đạt lại, điều kiện/ngoại lệ. Không đưa gold answer/source vào query hoặc filter. [Protocol](benchmark/protocol.md) ghi quy tắc và giới hạn; q16/q17 cùng trang và chủ đề dev/test có phần gần nhau.
- Tiêu chí chọn chiến lược đã chốt trước khi xem test: ưu tiên Evidence Hit@3 dev, sau đó Hit@1, rồi tài nguyên theo protocol. A được chọn từ dev và ghi trong [selection_decision.md](artifacts/selection_decision.md) trước test. [Experiment log](artifacts/experiment_log.csv) tổng hợp hồi cứu, không phải log giả thuyết có timestamp trước chạy. Không thay tham số sau xem test. Một hit tự động yêu cầu đúng source/page và đủ chuỗi evidence sau gộp khoảng trắng; evidence đa chunk không thay định nghĩa chính. Nhãn bằng chứng tương đương được ghi riêng, không ghi đè điểm tự động.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | 11/15 | 13/15 | 192 | Embed 9,097 s; DB write 0,190 s | API embedding 0 |
| A | test | 3/5 | 4/5 | 192 | Dùng index A đã nạp | API embedding 0 |
| B | dev | 7/15 | 9/15 | 202 | Embed 7,556 s; DB write 0,165 s | API embedding 0 |
| B | test | 2/5 | 4/5 | 202 | Dùng index B đã nạp | API embedding 0 |
| C | dev | 7/15 | 9/15 | 202, dùng lại B | Không tạo vector/bản ghi DB riêng | API embedding 0 |
| C | test | 2/5 | 4/5 | 202, dùng lại B | Dùng index B và filter | API embedding 0 |

Thời gian là các pha tạo embedding tài liệu/ghi DB của lần tái lập đã lưu, không phải thời gian dev/test hoặc tổng end-to-end. Không cộng chi phí B lần nữa cho C. Nguồn thời gian: `results/reproduced/embedding_runs.json`, `results/reproduced/database_ingest_runs.json`; số làm tròn cũng được ghi tại [final_summary.csv](results/final_summary.csv). Các lần chạy đơn không đủ để so hiệu suất phần cứng. [Kiểm tra chạy lại](results/recheck_validation.json) xác nhận toàn bộ điểm và thứ tự chunk top-3 dev/test khớp bản gốc.

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 1,0 (10) | 15/15 | 2/2 | 0: 1 câu; 1: 0; 2: 4; trung bình 1,6 |
| B | 1,1 (10) | 15/15 | 2/2 | 0: 0 câu; 1: 1; 2: 4; trung bình 1,8 |
| C | 1,1 (10) | 15/15 | 2/2 | 0: 0 câu; 1: 1; 2: 4; trung bình 1,8 |

Đường dẫn trace, nhãn thủ công và cách chọn mẫu: local có `results/dev_traces.jsonl` (45 trace), `results/test_traces.jsonl` (15 trace), `results/coherence_labels.csv` (30 nhãn), `results/grounding_labels.csv` (15 nhãn), `results/metadata_audit.csv` (45 kết quả). Coherence dùng cùng ký tự không trắng đầu tiên sau bỏ header trên trang 39–48, chọn chunk chứa vị trí có start offset nhỏ nhất. C dùng chunk/nhãn B. Grounding đọc top-3 của cùng 5 câu test; metadata kiểm tra source/page/section với nguồn cho cả 45 kết quả. Thang coherence/grounding 0–2, ghi từng lý do. Nhãn là Codex/AI-assisted content review, không giả thành chấm độc lập của học viên; chưa xác nhận học viên đã rà soát toàn bộ. [Coherence method](results/coherence_review_method.md), [grounding method](results/grounding_review_method.md), [metadata method](results/metadata_review_method.md). A/B không thực thi filter; tuân thủ quan sát 2/2 không chứng minh cơ chế lọc. Metadata đúng không đồng nghĩa chunk đủ evidence. Grounding đánh giá bằng chứng, không phải độ chính xác câu trả lời LLM.

## Phân tích và kết luận
- So sánh A–B và B–C; 2 ví dụ sai có ID câu và nguồn: A đạt dev Hit@3 13/15 so với B/C 9/15, test cùng 4/5; A test Hit@1 cao hơn (3/5 so với 2/5). B/C nhỉnh hơn coherence và grounding trong mẫu nhỏ. B–C có thay phạm vi kết quả ở một số câu nhưng chưa cải thiện điểm tổng hợp. **Lỗi A/q18:** nguồn đúng trang 67, Điều 37 về đề cương môn học, nhưng A top-3 lấy nội dung giảng dạy ở trang 50/52 nên grounding 0; B/C lấy được evidence ở rank 3. **Lỗi B/C/q19:** nguồn trang 68 về khóa áp dụng, chunk bị cắt trước năm tuyển sinh nên grounding 1; A lấy được bằng chứng đủ trong hai kết quả đầu. q06 dev có quote quá rộng: A top-1 đủ trả lời nhưng trượt khớp chuỗi; rà soát tương đương lưu riêng `results/dev_manual_review.csv` và giữ nguyên bảng điểm tự động.
- Chiến lược chọn, đánh đổi, điều kiện áp dụng: chọn A theo dev, không chọn lại bằng test. Overlap tăng lượng ký tự embedding (86.674 so với 78.999) nhưng giữ evidence tốt hơn trong các kết quả đã đo. Không kết luận A thắng mọi tiêu chí hoặc tốt nhất với corpus khác. Filter `section` hữu ích để kiểm soát phạm vi nhưng không sửa nội dung bị cắt.
- Hạn chế của dữ liệu, nhãn, test nhỏ, đo thời gian/chi phí: một handbook và 5 test, câu hỏi tập trung một số trang; sample coherence đầu trang thiên về heading/nội dung nối trang; chia đoạn dài vẫn cắt từ/câu. Text extraction có lỗi khoảng trắng và bảng. Nhãn AI có nguy cơ thiên lệch, chưa phải human audit độc lập; đối chiếu PDF chủ yếu bằng text phân trang/ảnh người học gửi, không kiểm tra hình ảnh toàn bộ trang. Thời gian một lần có ảnh hưởng cache/CPU; chưa đo điện/phần cứng. License và bàn giao minh chứng chưa hoàn tất. Commit chốt và việc nộp repo cần học viên xác nhận.
- Nếu làm lại hoặc mở rộng, cải tiến gì? Xác minh quyền và cách chia sẻ trước; ghi log giả thuyết trước chạy; mở rộng test nhiều trang/chủ đề; cải thiện tách câu/heading và xử lý bảng, chọn tham số trên dev; rà soát mù nhãn bởi người học. Nếu đổi cấu hình sau khi đã xem test, phải công bố và dùng test mới cho đánh giá độc lập. Codex hỗ trợ giải thích đề, code, soạn benchmark, phân tích và nhãn audit; Copilot SDK hỗ trợ tài liệu/báo cáo. Học viên chạy lệnh, phản hồi kết quả và đối chiếu một số trang; mức kiểm chứng được khai báo đúng thực tế, không bịa nhãn hoặc số liệu.
