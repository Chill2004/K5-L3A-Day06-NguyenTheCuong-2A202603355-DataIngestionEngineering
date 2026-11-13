# Kiểm tra nạp lại

- Nạp lại toàn bộ cùng corpus, chunk và vector.
- Trước nạp lại: A = 192 bản ghi; B = 202 bản ghi.
- Sau nạp lại: A = 192 bản ghi; B = 202 bản ghi.
- Kết luận: lần nạp lại được kiểm tra không làm tăng số bản ghi.
- Cơ chế: thay thế toàn bộ chunk của tài liệu trong từng strategy,
  thực hiện trong transaction.
- C tái sử dụng dữ liệu B nên không lưu bản sao riêng.