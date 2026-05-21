# Ứng dụng OCR trích xuất văn bản

App là một trang web nhỏ chạy bằng Streamlit, cho phép tải ảnh hoặc PDF lên, sau đó dùng EasyOCR đọc chữ và trả về dạng text.

## Cài đặt và chạy

Tạo môi trường ảo rồi cài thư viện:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Lần đầu chạy, EasyOCR sẽ tải model về 
Sau đó, browser sẽ tự mở `http://localhost:8501`.

## Các thư viện chính

App dùng **EasyOCR** làm engine nhận dạng. EasyOCR thực ra là pipeline 2 model
ghép lại: CRAFT để tìm vị trí từng vùng chữ trong ảnh (detection), rồi CRNN để
đọc nội dung của từng vùng đó (recognition). Em chọn nó vì nó hỗ trợ sẵn tiếng
Việt mà không cần train lại, cài bằng pip cũng đơn giản, không phải chạy installer
như Tesseract.

UI thì dùng **Streamlit** — viết python thuần là ra web, đỡ phải đụng vào
HTML/CSS/JS. Phần xử lý ảnh dùng **OpenCV** (đổi grayscale, khử nhiễu, threshold,
CLAHE). Với PDF, em dùng **PyMuPDF** (`fitz`) để render từng trang thành ảnh
trước khi đưa vào EasyOCR — PyMuPDF tiện vì không cần cài Poppler/Ghostscript bên
ngoài như `pdf2image`.

## Quy trình xử lý

Khi user upload file lên, app sẽ phân biệt là ảnh hay PDF:

- Nếu là **ảnh**, đọc bằng Pillow, convert sang numpy BGR để OpenCV xử lý.
- Nếu là **PDF**, dùng PyMuPDF render các trang được chọn ra ảnh ở DPI tự đặt
  (mặc định 200). Ở DPI 200 chất lượng OCR đã khá ổn, lên 300+ thì chậm hơn nhiều
  mà cải thiện không đáng kể.

Tiếp theo là bước tiền xử lý. App có 5 chế độ:

- *Giữ nguyên* — đưa thẳng ảnh gốc vào OCR.
- *Grayscale* — chuyển ảnh xám, giảm nhiễu màu.
- *Khử nhiễu* — dùng `cv2.fastNlMeansDenoising`, hợp với ảnh chụp điện thoại bị
  hạt.
- *Nhị phân (Adaptive)* — threshold theo vùng cục bộ, hữu ích khi ánh sáng không
  đều.
- *Tăng tương phản (CLAHE)* — cân bằng histogram theo block, cứu được ảnh tối.

Cuối cùng app vẽ bounding box màu (xanh nếu conf ≥ 70%, cam nếu 40–70%, đỏ nếu
dưới 40%) lên ảnh đã xử lý, đồng thời hiển thị text trong textarea và bảng chi
tiết, cho phép tải về `.txt`.


## Cấu trúc dự án

```
ocr-app/
├── app.py              # toàn bộ logic + UI Streamlit
├── requirements.txt    # 6 thư viện
├── README.md
└── .streamlit/
    └── config.toml     # tắt usage stats
```
