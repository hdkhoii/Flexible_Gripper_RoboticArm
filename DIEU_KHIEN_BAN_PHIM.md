# Dieu khien tay may bang ban phim

## Cach chay

1. Nap firmware vao Arduino bang nut **PlatformIO: Upload**.
2. Dong Serial Monitor neu dang mo (mot cong COM khong the mo boi hai chuong trinh).
3. Mo terminal tai thu muc du an va chay:

   ```powershell
   python keyboard_control.py
   ```

Chuong trinh se tu dong tim Arduino Uno. Neu can chi dinh cong thu cong:

```powershell
python keyboard_control.py --port COM3
```

## Phim dieu khien

| Khop | Giam | Tang |
|---|---:|---:|
| Ban kep | Q | A |
| Co tay | W | S |
| Khuyu tay | E | D |
| Vai | R | F |
| De xoay | T | G |

- Giu phim de chuyen dong lien tuc; tha phim de dung.
- Co the giu nhieu phim de dieu khien nhieu khop cung luc.
- `0`: dua muot tat ca khop ve 0 do.
- `9`: dua muot tat ca khop ve 90 do.
- `1`, `2`, `3`, `4`: chon toc do 25, 50, 80 hoac 120 do/giay.
- `Esc`: dung va dong chuong trinh.

Toc do mac dinh la muc 3 (80 do/giay). Firmware tu dong tang va giam toc
voi gia toc 300 do/giay^2 de servo khoi giat khi bam hoac tha phim. Toc do
thuc te con phu thuoc vao thong so va tai co khi cua tung servo.

Cua so dieu khien phai dang duoc focus. Khi cua so mat focus hoac ket noi bi
ngat, lenh dieu khien duoc xoa; Arduino cung tu dung sau 250 ms neu khong con
nhan duoc du lieu.
