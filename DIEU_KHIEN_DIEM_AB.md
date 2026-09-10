# Gắp vật từ điểm A sang điểm B

## Chuẩn bị

1. Nạp firmware mới trong `src/main.cpp` vào Arduino bằng **PlatformIO: Upload**.
2. Đóng Serial Monitor và chạy:

   ```powershell
   python slider_control.py
   ```

   Nếu chương trình không tự tìm đúng cổng:

   ```powershell
   python slider_control.py --port COM3
   ```

## Dạy robot

Luôn thử lần đầu khi chưa có vật và để tay gần nút **DỪNG KHẨN CẤP**.

1. Dùng các slider đưa đầu kẹp đến vị trí lấy vật, rồi bấm **Lưu điểm A**.
2. Đưa đầu kẹp đến vị trí thả vật, rồi bấm **Lưu điểm B**.
3. Đưa robot lên một tư thế cao, không vướng bàn hay vật cản, rồi bấm
   **Lưu điểm SAFE**. Nếu không lưu, chương trình dùng tư thế khởi động.
4. Dùng slider `Hand` mở kẹp đến mức phù hợp, rồi bấm **Lưu góc MỞ kẹp**.
5. Dùng slider `Hand` đóng kẹp vừa đủ giữ vật, rồi bấm
   **Lưu góc ĐÓNG kẹp**. Không ép servo quá chặt.
6. Bấm **CHẠY A -> B**.

Chu trình thực hiện là:

```text
Mở kẹp -> SAFE -> A -> đóng kẹp -> SAFE -> B -> mở kẹp -> SAFE
```

Chương trình chỉ chuyển bước sau khi tất cả khớp liên quan đã nằm trong sai số
2 độ qua ba lần phản hồi liên tiếp. Nếu một bước kéo dài quá 20 giây, robot sẽ
dừng. Nút **DỪNG KHẨN CẤP** gửi lệnh `X` để hủy các góc đích đang chạy.

Các điểm chỉ được lưu trong phiên chạy hiện tại. Khi đóng chương trình, cần dạy
lại A, B và hai góc kẹp ở lần mở sau.
