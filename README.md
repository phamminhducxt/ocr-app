# Ứng dụng OCR trích xuất văn bản

Đây là đề tài báo cáo thực tập của em. App là một trang web nhỏ chạy bằng Streamlit,
cho phép tải ảnh hoặc PDF lên, sau đó dùng EasyOCR đọc chữ và trả về dạng text. Hỗ
trợ tiếng Việt có dấu là yêu cầu chính, nên em chọn EasyOCR thay vì Tesseract.

## Cài đặt và chạy

App đang đặt ở `D:\ClaudeCode\projects\ocr-app`. Tạo môi trường ảo rồi cài thư viện:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Lần đầu chạy, EasyOCR sẽ tải model về (khoảng 64MB mỗi ngôn ngữ), nên cần Internet
và phải đợi một chút. Sau đó các lần sau sẽ nhanh vì model được cache trong
`C:\Users\<user>\.EasyOCR\model\`. Browser sẽ tự mở `http://localhost:8501`.

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

Em để mặc định là "Giữ nguyên" vì test thử thấy EasyOCR vốn đã xử lý nội bộ khá
tốt, đôi khi tiền xử lý ngược lại làm mất chữ. Các chế độ kia chỉ bật khi ảnh
thật sự khó.

Sau đó EasyOCR trả về list `(bbox, text, confidence)` cho mỗi vùng chữ tìm được.
App lọc theo ngưỡng confidence (mặc định 0.3) rồi nhóm các box gần nhau theo
trục Y thành dòng, mỗi dòng sort lại theo trục X — như vậy khi xuất text ra sẽ
theo thứ tự đọc tự nhiên thay vì thứ tự ngẫu nhiên model trả về.

Cuối cùng app vẽ bounding box màu (xanh nếu conf ≥ 70%, cam nếu 40–70%, đỏ nếu
dưới 40%) lên ảnh đã xử lý, đồng thời hiển thị text trong textarea và bảng chi
tiết, cho phép tải về `.txt`.

## Khó khăn gặp phải

- **Lỗi Unicode khi tải model**. Lần đầu chọn tiếng Anh, app crash với
  `UnicodeEncodeError: 'charmap' codec can't encode character '█'`. Nguyên
  nhân là tqdm progress bar của EasyOCR dùng ký tự `█`, mà stdout Streamlit trên
  Windows lại default codec `cp1252` không có ký tự đó. Em fix bằng cách
  `sys.stdout.reconfigure(encoding="utf-8")` ngay đầu file, và thêm
  `PYTHONIOENCODING=utf-8` trong `.vscode/settings.json` để terminal cũng UTF-8.
- **Streamlit hỏi email lần đầu chạy**. Cái welcome banner của Streamlit hỏi
  nhập email cho onboarding, gây kẹt khi launch bằng VSCode task. Tạo file
  `~/.streamlit/credentials.toml` với email rỗng là skip được.
- **Thứ tự đọc text**. Ban đầu xuất text theo đúng thứ tự EasyOCR trả về thì
  thấy lộn xộn, ví dụ ảnh hóa đơn thì các dòng nhảy linh tinh. Em viết hàm
  `group_by_lines` để nhóm box theo Y rồi sort X trong từng dòng — kết quả đọc
  thuận hơn nhiều.

## Định hướng mở rộng

Hiện app đã chạy ổn với ảnh và PDF nhiều trang. Một số hướng có thể làm tiếp
nếu còn thời gian: cho phép upload nhiều ảnh cùng lúc (batch), export ra Word
hoặc Excel thay vì chỉ `.txt`, và xa hơn là fine-tune model riêng cho các loại
giấy tờ tiếng Việt phổ biến (hóa đơn, CMND, CCCD) để đạt độ chính xác cao hơn
mức EasyOCR mặc định.

## Cấu trúc dự án

```
ocr-app/
├── app.py              # toàn bộ logic + UI Streamlit
├── requirements.txt    # 6 thư viện
├── README.md
└── .streamlit/
    └── config.toml     # tắt usage stats
```
