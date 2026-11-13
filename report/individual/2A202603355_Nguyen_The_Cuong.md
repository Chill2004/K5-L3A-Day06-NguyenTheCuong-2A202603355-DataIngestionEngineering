# Báo cáo cá nhân — Day 06 Data Ingestion Engineering

- Họ tên: Nguyễn Thế Cường
- MSSV: 2A202603355
- Lớp: L3A
- Chủ đề: Sổ tay sinh viên 2024 — Trường Đại học Mở TP.HCM

Hướng dẫn chạy và báo cáo theo mẫu: [REPORT_TEMPLATE.md](../../REPORT_TEMPLATE.md).
README.md của đề được giữ nguyên.
Schema/nguồn giá trị metadata: [metadata_schema.json](../../artifacts/metadata_schema.json).
Trạng thái quyền và giới hạn bàn giao được trình bày trong báo cáo này và
[REPORT_TEMPLATE.md](../../REPORT_TEMPLATE.md); các ghi chú làm việc riêng không push.

## Dữ liệu và pipeline

Nguồn là PDF do Trường Đại học Mở TP.HCM lưu trữ tại
<https://ou.edu.vn/wp-content/uploads/2024/09/So-Tay-SV-2024.pdf>. Manifest
ghi 167 trang vật lý và chọn 39 trang PDF 39–77; tổng ký tự ghi trong manifest
là 79.077. Các trang được đọc và kiểm tra theo manifest; section splitter tạo
40 đơn vị nguồn. Đã tìm thấy điều khoản sử dụng cá nhân, không kinh doanh trong
quy định website trường; chưa xác minh giấy phép mở hoặc quyền riêng cho embedding
và tái phân phối (xem [kiểm tra license](../../data/LICENSE_REVIEW.md)).
PDF, benchmark chứa evidence và nội dung phái sinh được giữ local,
không đưa lên repo cho đến khi xác minh quyền.

Pipeline đọc PDF bằng `pypdf`, chuẩn hóa và tách section, giữ document ID,
source, số trang, section, unit ID và offsets. `python -m src.run --stage prepare`
kiểm tra tối thiểu 30 trang, benchmark dev/test, filter và evidence, sau đó
xác nhận chunk bao phủ nội dung không phải khoảng trắng. Lần chuẩn bị được ghi
nhận tạo A: 192 chunks và B: 202 chunks, khớp với kết quả đã lưu.

Embedding dùng `intfloat/multilingual-e5-small`, revision
`614241f622f53c4eeff9890bdc4f31cfecc418b3`, 384 chiều, CPU, L2 normalization;
document/query prefix lần lượt là `passage: ` và `query: `. Vector store là
PostgreSQL 16.16 + pgvector 0.8.7, exact cosine search, top-3. Filter bổ sung
là `section`, lấy từ heading đã tách trong handbook; cùng `source` và `page`
giúp truy vết. Chi phí API là 0; điện và phần cứng không được ước tính.

Bằng chứng kiểm tra local riêng được lưu tại
[local_model_verification.json](../../artifacts/local_model_verification.json):
một query kiểm tra mới chạy CPU với chế độ offline và chặn kết nối socket trong
tiến trình. Kiểm tra này không thay thế log lịch sử của toàn bộ corpus.

## Cấu hình, benchmark và quy trình chọn

| Cấu hình | Chunking | Filter |
|---|---|---|
| A | Fixed-size 500 ký tự, overlap 50 | Không |
| B | Theo paragraph, tối đa 500 ký tự; paragraph dài chia thành cửa sổ cân bằng | Không |
| C | Dùng lại chunk và vector của B | Dùng `section` khi câu hỏi có filter |

Benchmark có 20 câu (15 dev, 5 test), gồm 5 câu có filter (3 dev, 2 test).
Evidence được kiểm tra với text trích xuất trước khi chạy. Tiêu chí chọn cấu
hình là Evidence Hit@3 dev, sau đó Hit@1. A được chọn trên dev; quyết định được
lưu trước lần chạy test. Experiment log hiện tại được tổng hợp hồi cứu; giả
thuyết trong log không phải bản ghi có timestamp trước khi chạy.

## Kết quả retrieval

| Strategy | Dev Hit@1 | Dev Evidence Hit@3 | Test Hit@1 | Test Evidence Hit@3 | Chunks | Ký tự chunk | Embed (s) | DB write (s) | Chi phí API embedding |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 11/15 | 13/15 | 3/5 | 4/5 | 192 | 86.674 | 9,097 | 0,190 | 0 |
| B | 7/15 | 9/15 | 2/5 | 4/5 | 202 | 78.999 | 7,556 | 0,165 | 0 |
| C | 7/15 | 9/15 | 2/5 | 4/5 | 202 | 78.999 | Dùng lại B | Dùng lại B | 0 |

Thời gian embedding và DB write lấy từ lần tái lập cuối trong
`results/reproduced/embedding_runs.json` và
`results/reproduced/database_ingest_runs.json`; đây là một lần chạy local,
không phải benchmark phần cứng. C dùng lại vectors/store của B, nên không có
lượt embedding hoặc bản ghi DB độc lập.

Lượt kiểm tra cuối đã chạy lại phần chuẩn bị và retrieval dev/test với model
local trong cache, lưu riêng tại `results/recheck/`. Cả sáu cặp cấu hình/split
giữ nguyên Hit@1/Hit@3 và thứ tự chunk top-3 so với lần gốc. Xem
`results/recheck_validation.json`. Không sinh lại embedding tài liệu hoặc nạp
lại DB trong lượt kiểm tra này vì hash chunk/model không đổi; các vector đã
được kiểm tra ID, số chiều và chuẩn L2 bằng `scripts/verify_artifacts.ps1`.

Lần chạy `python -m src.run --stage all` cuối hoàn tất thành công: 39 trang,
40 sections, 20 evidence checks; tạo 192/202 vectors, mỗi vector 384 chiều,
và PostgreSQL báo 192 bản ghi A, 202 bản ghi B. Các output được ghi riêng dưới
`results/reproduced/`, không ghi đè traces/kết quả thí nghiệm ban đầu.

## Audit năm khía cạnh

| Strategy | Coherence trung bình /2 (n=10) | Metadata đủ/đúng (n=15) | Tuân thủ filter (n=2) | Grounding 0/1/2 (n=5) | Grounding trung bình /2 |
|---|---:|---:|---:|---|---:|
| A | 1,0 | 15/15 | 2/2 | 1 / 0 / 4 | 1,6 |
| B | 1,1 | 15/15 | 2/2 | 0 / 1 / 4 | 1,8 |
| C | 1,1 | 15/15 | 2/2 | 0 / 1 / 4 | 1,8 |

- **Retrieval accuracy:** A tốt hơn B trên dev; trên test A/B/C cùng Evidence
  Hit@3 4/5, còn Hit@1 lần lượt 3/5, 2/5, 2/5. Đây là evidence retrieval,
  không phải độ chính xác câu trả lời do LLM sinh.
- **Chunk coherence:** mẫu gồm 10 vị trí đầu nội dung trên các trang PDF 39–48.
  B/C cao hơn A 0,1 điểm trong mẫu nhỏ này; C dùng cùng chunk B nên dùng cùng
  nhãn coherence.
- **Metadata usefulness:** 45 kết quả top-3 trên test được kiểm tra source,
  page, section và offsets; đủ/đúng 15/15 mỗi strategy. Source/page hỗ trợ truy
  vết, section hỗ trợ thu hẹp phạm vi; section vẫn phụ thuộc chất lượng heading
  và không bổ sung evidence bị thiếu trong chunk.
- **Filter:** hai câu test có filter cho kết quả tuân thủ 2/2 ở cả A/B/C.
  A/B không thực thi filter; kết quả phù hợp quan sát được không chứng minh
  filter enforcement. C dùng filter của câu hỏi; B–C không làm thay đổi điểm
  retrieval tổng thể trong số liệu này.
- **Grounding quality:** nhãn đánh giá mức evidence trong top-3: 0 = không có,
  1 = thiếu điều kiện/ngữ cảnh, 2 = đủ để trả lời và truy nguồn. Nhãn coherence
  và grounding được ghi là AI-assisted content review, không phải đánh giá
  độc lập của người; cần được học viên kiểm tra lại trước khi nộp.

## Lỗi quan sát được, kết luận và giới hạn

1. **A/q18:** top-3 không có yêu cầu về đề cương học phần đã công bố, grounding
   0; B/C tìm được evidence ở hạng 3 và grounding 2.
2. **B/C/q19:** đoạn về phạm vi áp dụng bị cắt trước năm tuyển sinh, grounding
   1; không thể suy năm áp dụng từ năm trong tiêu đề handbook. A lấy được điều
   kiện trong hai kết quả đầu và grounding 2.

A là lựa chọn theo tiêu chí dev đã ghi, nhưng không thắng mọi tiêu chí: B/C
nhỉnh hơn coherence và grounding trong audit nhỏ, trong khi B/C không tăng
Evidence Hit@3 trên test và filter không cải thiện điểm tổng hợp. A–B đồng thời
thay chunking và overlap nên không cô lập riêng ảnh hưởng của overlap. C chỉ
thay filter so với B.

Giới hạn chính: một handbook, 39 trang đã chọn, chỉ năm câu test và test tập
trung vào một số trang; q16/q17 cùng trang nguồn. Nhãn coherence/grounding có
thiên lệch do AI assistance, không phải chấm độc lập. Benchmark q06 có evidence
quote rộng; điểm khớp chuỗi tự động được giữ nguyên và rà soát riêng. Log giả
thuyết được tổng hợp hồi cứu. PDF renderer cục bộ không hoạt động trong lần
audit, nên đối chiếu dựa trên text trích xuất và nguồn PDF; không tuyên bố đã
kiểm tra trực quan toàn bộ PDF. Quyền tái phân phối chưa xác minh, nên người
khác không thể tái lập từ repo trống nếu chưa có corpus/benchmark được phép.

Nếu làm lại, cần xác minh quyền trước, mở rộng test sang nhiều trang/chủ đề,
rà soát mù nhãn thủ công độc lập, và ghi giả thuyết/thời gian ingest ngay trước
khi chạy. Không suy rộng kết quả này ra corpus khác.

## Khai báo sử dụng AI

Copilot SDK trong VS Code hỗ trợ tiếp tục tài liệu, rà soát số liệu đã lưu và
soạn báo cáo này. Các file audit hiện có ghi reviewer là AI-assisted/Codex;
không trình bày các nhãn đó như đánh giá độc lập của học viên. Học viên cần
rà soát nội dung và cập nhật khai báo để phản ánh đầy đủ mọi công cụ AI đã
dùng trong toàn bộ bài làm.

Codex trong hội thoại hỗ trợ đọc đề, viết và sửa pipeline, soạn bản nháp bộ câu
hỏi/evidence, kiểm tra chuỗi evidence, phân tích trace, chấm nội dung coherence,
grounding và rà soát metadata. Học viên đã thực hiện các lệnh chạy và phản hồi
kết quả; đã cung cấp ảnh đối chiếu một số trang PDF. Các nhãn AI được công bố
đúng phương pháp, chưa xác nhận toàn bộ nhãn đã được học viên rà soát độc lập.
Không mô tả chúng là kết quả chấm mù của một người đánh giá độc lập.
