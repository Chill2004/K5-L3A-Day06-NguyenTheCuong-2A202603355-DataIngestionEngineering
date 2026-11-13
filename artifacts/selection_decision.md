# Quyết định chọn cấu hình trước test

## Kết quả dev tự động
| Strategy | Hit@1 | Evidence Hit@3 |
|---|---|---|
| A | 11/15 | 13/15 |
| B | 7/15 | 9/15 |
| C | 7/15 | 9/15 |

## Quyết định
- Chọn A theo tiêu chí ưu tiên Evidence Hit@3, sau đó Hit@1.
- Quyết định dựa trên dev, chưa chạy retrieval trên test.
- Không thay đổi chunking, embedding hoặc filter sau quyết định này.
- Chạy cả A/B/C đã cố định trên cùng năm câu test.

## Cấu hình cố định
- A: fixed-size 500 ký tự, overlap 50, không filter.
- B: theo đoạn, tối đa 500 ký tự, chia cân bằng đoạn quá dài,
  không overlap, không filter.
- C: tái sử dụng chunk/vector B; áp dụng filter từ câu hỏi nếu có.
- Model: intfloat/multilingual-e5-small.
- Revision: 614241f622f53c4eeff9890bdc4f31cfecc418b3.
- Vector: 384 chiều, chuẩn hóa L2.
- Query prefix: "query: ".
- Document prefix: "passage: ".
- Store: PostgreSQL 16.16 + pgvector 0.8.7.
- Search: exact cosine, top-3.

## Quan sát và giới hạn
- A/q06 có bằng chứng đủ trả lời nhưng trượt khớp chuỗi vì gold quote
  quá rộng; nhãn rà soát được lưu riêng, không ghi đè điểm tự động.
- B/C có trường hợp cắt giữa điều kiện hoặc câu trả lời.
- Metadata filter có thay đổi phạm vi kết quả nhưng chưa cải thiện
  Hit@1/Hit@3 tổng thể trên dev.
- Kết quả chỉ áp dụng cho corpus và benchmark hiện tại.