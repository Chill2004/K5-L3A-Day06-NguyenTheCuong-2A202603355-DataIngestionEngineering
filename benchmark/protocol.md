# Quy tắc benchmark

## Corpus
- Nguồn: Sổ tay sinh viên 2024, Trường Đại học Mở TP.HCM.
- source_id: ou_handbook_2024.
- Phạm vi: trang PDF 39–77, gồm 39 trang vật lý.
- Trang 68 được tách thành hai đoạn nguồn theo heading.
- Tổng cộng 40 đoạn nguồn trong results/sections.jsonl.

## Bộ câu hỏi
- File: benchmark/questions.jsonl.
- Dev: q01–q15, gồm 15 câu.
- Test: q16–q20, gồm 5 câu.
- Câu có filter: q01, q03, q06, q16, q18.
- Cả 20 evidence đã qua kiểm tra tồn tại trong text trích xuất.
- Việc đối chiếu nội dung và đáp án với PDF phải hoàn tất trước khi chạy retrieval.
- Một số evidence giữ nguyên khoảng trắng lỗi từ PDF extraction.

## Cấu hình thí nghiệm
- A: chunk kích thước cố định, không filter.
- B: chunk theo đoạn, không filter.
- C: dùng cùng chunk và vector với B; chỉ áp dụng filter khi câu hỏi cung cấp.
- Câu không có filter: C chạy không filter.
- Giữ nguyên corpus, chuẩn hóa, embedding model, vector store,
  metric cosine và top-k = 3 giữa các cấu hình.

## Quy tắc tính hit
- Chunk phải đúng nguồn/trang và chứa đủ evidence hỗ trợ đáp án.
- Bằng chứng tương đương cần được kiểm chứng và ghi nhận.
- Đúng trang nhưng thiếu evidence không được tính hit.
- Evidence bị tách qua nhiều chunk không được tính là một chunk hit.
- Báo Hit@1 và Evidence Hit@3 riêng cho dev và test, có số tử/mẫu.

## Chọn cấu hình
- Chỉ dùng kết quả dev để điều chỉnh.
- Ưu tiên Evidence Hit@3 trên dev.
- Nếu bằng nhau, ưu tiên Hit@1 trên dev.
- Nếu vẫn bằng nhau, ưu tiên tổng ký tự cần embedding thấp hơn.
- Nếu vẫn bằng nhau, giữ các cấu hình đồng hạng.
- Cố định tham số và ghi quyết định trước khi chạy test.
- Chạy cả A/B/C đã cố định trên test; không dùng test để tinh chỉnh.

## Mẫu coherence
- Chọn trước 10 vị trí: ký tự không trắng đầu tiên sau header
  trong từng đoạn nguồn của các trang PDF 39–48.
- Dùng cùng vị trí nguồn để đánh giá A/B/C.
- Nếu nhiều chunk chứa cùng vị trí, chọn chunk có thứ tự nhỏ nhất
  theo vị trí bắt đầu trong nguồn.
- Chấm 0–2, lưu nhãn và lý do.

## Giới hạn
- Chỉ có một tài liệu và năm câu test.
- Một số câu dev/test gần chủ đề; q16 và q17 cùng trang nguồn.
- Bộ câu hỏi tập trung vào một số trang trong corpus.
- Người học tự chấm, có nguy cơ thiên lệch.
- Không suy rộng kết quả ra mọi tài liệu.

## Quan sát chunking trước retrieval
- A: 192 chunk, tổng 86.674 ký tự.
- B: 202 chunk, tổng 78.999 ký tự.
- C tái sử dụng chunk và vector của B.
- Cả A/B đã kiểm tra bao phủ đủ ký tự nội dung nguồn.
- B còn 5 chunk dưới 50 ký tự: heading, tiêu đề bảng và khoảng điểm.
- Giữ nguyên các chunk này và ghi nhận nguy cơ thiếu ngữ cảnh.
- A và B khác cả cách chia đoạn và overlap; so sánh A–B đánh giá
  tổng thể hai cấu hình chunking, không tách riêng ảnh hưởng overlap.
- B–C chỉ thay việc áp dụng metadata filter.

## Rà soát sau lần chạy dev đầu
- Phát hiện evidence q06 được chọn quá rộng khi chuẩn bị benchmark.
- Giữ nguyên gold và các chỉ số tự động của lần chạy đầu để truy vết.
- A/q06/top-1 được rà soát là bằng chứng tương đương đủ trả lời;
  ghi nhãn riêng trong results/dev_manual_review.csv.
- Chỉ số sau rà soát phải được báo riêng với chỉ số khớp chuỗi tự động.
- B/C vẫn không hit q06 vì top-3 không chứa bằng chứng trả lời.
- q14 ở B/C có evidence chia qua hai chunk; không tính là single-chunk hit.