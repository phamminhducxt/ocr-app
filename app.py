# App OCR - đồ án thực tập (Phạm Minh Đức)
# Dùng EasyOCR đọc chữ, Streamlit làm UI, PyMuPDF để render PDF
import io
import sys
import time

# Streamlit chạy non-tty trên Win nên stdout default về cp1252,
# tqdm progress bar của EasyOCR có ký tự █ -> crash. Ép utf-8 ngay từ đầu.
for s in (sys.stdout, sys.stderr):
    if s is not None and hasattr(s, "reconfigure"):
        s.reconfigure(encoding="utf-8", errors="replace")

import cv2
import easyocr
import fitz  # PyMuPDF
import numpy as np
import streamlit as st
from PIL import Image

st.set_page_config(page_title="OCR - Trích xuất văn bản", layout="wide")


@st.cache_resource(show_spinner="Đang tải mô hình OCR (lần đầu sẽ tải ~64MB)...")
def load_reader(languages):
    return easyocr.Reader(list(languages), gpu=False)


def preprocess(img_bgr, mode):
    if mode == "Giữ nguyên":
        return img_bgr
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    if mode == "Grayscale":
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    if mode == "Khử nhiễu":
        denoised = cv2.fastNlMeansDenoising(gray, h=15)
        return cv2.cvtColor(denoised, cv2.COLOR_GRAY2BGR)
    if mode == "Nhị phân (Adaptive)":
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
        )
        return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    if mode == "Tăng tương phản (CLAHE)":
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
    return img_bgr


def draw_boxes(img_bgr, results):
    out = img_bgr.copy()
    for bbox, _text, conf in results:
        pts = np.array(bbox, dtype=np.int32)
        # xanh = chắc chắn, cam = ngờ ngợ, đỏ = lởm
        if conf >= 0.7:
            color = (0, 200, 0)
        elif conf >= 0.4:
            color = (0, 165, 255)
        else:
            color = (0, 0, 255)
        cv2.polylines(out, [pts], True, color, 2)
    return out


def group_by_lines(results, tol_ratio=0.5):
    # gom các box gần nhau theo trục Y thành 1 dòng, sau đó sort trái->phải
    if not results:
        return []
    items = []
    for bbox, text, conf in results:
        ys = [p[1] for p in bbox]
        xs = [p[0] for p in bbox]
        y_c = (min(ys) + max(ys)) / 2
        x_l = min(xs)
        h = max(ys) - min(ys)
        items.append((y_c, x_l, h, bbox, text, conf))
    avg_h = sum(it[2] for it in items) / len(items)
    tol = avg_h * tol_ratio
    items.sort(key=lambda it: it[0])
    lines = [[items[0]]]
    for it in items[1:]:
        if it[0] - lines[-1][-1][0] <= tol:
            lines[-1].append(it)
        else:
            lines.append([it])
    for ln in lines:
        ln.sort(key=lambda x: x[1])
    return [[(bbox, text, conf) for _, _, _, bbox, text, conf in ln] for ln in lines]


def pdf_to_images(file_bytes, dpi, page_start, page_end):
    # render từng trang PDF ra ảnh numpy (BGR) để OCR
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    imgs = []
    for i in range(page_start - 1, page_end):
        pix = doc[i].get_pixmap(matrix=mat, alpha=False)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
        elif pix.n == 3:
            arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        else:
            arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
        imgs.append(arr)
    doc.close()
    return imgs


def render_page_result(p, file_stem):
    st.caption(
        f"{p['label']} — {len(p['filtered'])} vùng / {len(p['lines'])} dòng "
        f"(lọc từ {len(p['results'])}) • {p['elapsed']:.2f}s"
    )

    col_a, col_b = st.columns([1, 1])
    with col_a:
        st.markdown("Vị trí văn bản")
        annotated = draw_boxes(p["processed_bgr"], p["sorted_items"])
        st.image(cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB), use_container_width=True)

    with col_b:
        st.markdown("Văn bản trích xuất")
        page_text = "\n".join(" ".join(text for _, text, _ in ln) for ln in p["lines"])
        st.text_area(
            "Kết quả", page_text, height=300,
            label_visibility="collapsed",
            key=f"text_{p['label']}",
        )
        st.download_button(
            f"Tải {p['label']}.txt",
            data=page_text.encode("utf-8"),
            file_name=f"{file_stem}_{p['label'].replace(' ', '_').lower()}.txt",
            mime="text/plain",
            use_container_width=True,
            key=f"dl_{p['label']}",
        )

    if p["sorted_items"]:
        with st.expander("Chi tiết từng vùng"):
            line_idx = []
            for i, ln in enumerate(p["lines"], 1):
                line_idx.extend([i] * len(ln))
            table = [
                {
                    "STT": i + 1,
                    "Dòng": line_idx[i],
                    "Văn bản": text,
                    "Độ tin cậy": f"{conf:.1%}",
                }
                for i, (_, text, conf) in enumerate(p["sorted_items"])
            ]
            st.dataframe(table, use_container_width=True, hide_index=True)


st.title("Trích xuất văn bản từ ảnh / PDF")

with st.sidebar:
    st.header("Cấu hình")
    lang_choice = st.radio(
        "Ngôn ngữ",
        ["Tiếng Việt", "Tiếng Anh", "Việt + Anh"],
        index=0,
    )
    lang_map = {
        "Tiếng Việt": ("vi",),
        "Tiếng Anh": ("en",),
        "Việt + Anh": ("vi", "en"),
    }
    languages = lang_map[lang_choice]

    preprocess_mode = st.selectbox(
        "Tiền xử lý",
        ["Giữ nguyên", "Grayscale", "Khử nhiễu", "Nhị phân (Adaptive)", "Tăng tương phản (CLAHE)"],
        index=0,
    )

    conf_threshold = st.slider(
        "Ngưỡng tin cậy", 0.0, 1.0, 0.3, 0.05,
        help="Box nào dưới ngưỡng sẽ bị bỏ",
    )

    pdf_dpi = st.slider(
        "DPI render PDF", 100, 400, 200, 50,
        help="Cao hơn = nét hơn nhưng chậm",
    )

    st.markdown("---")
    st.caption("Màu box: xanh ≥ 70%, cam 40-70%, đỏ < 40%")

uploaded = st.file_uploader(
    "Chọn ảnh hoặc PDF",
    type=["png", "jpg", "jpeg", "bmp", "webp", "pdf"],
)

if uploaded is None:
    st.info("Tải lên ảnh hoặc PDF để bắt đầu.")
    st.stop()

file_ext = uploaded.name.rsplit(".", 1)[-1].lower()
file_stem = uploaded.name.rsplit(".", 1)[0]
is_pdf = file_ext == "pdf"

if is_pdf:
    file_bytes = uploaded.getvalue()
    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            total_pages = doc.page_count
    except Exception as e:
        st.error(f"Không đọc được PDF: {e}")
        st.stop()

    st.write(f"PDF có {total_pages} trang.")

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        page_start = st.number_input(
            "Trang đầu", min_value=1, max_value=total_pages, value=1, step=1,
        )
    with col_p2:
        # mặc định 5 trang vì OCR nhiều quá chờ lâu
        page_end = st.number_input(
            "Trang cuối", min_value=1, max_value=total_pages,
            value=min(total_pages, 5), step=1,
        )

    if page_end < page_start:
        st.error("Trang cuối phải >= trang đầu")
        st.stop()

    with st.spinner(f"Đang render trang {page_start}-{page_end} ({pdf_dpi} DPI)..."):
        pages_bgr = pdf_to_images(file_bytes, pdf_dpi, page_start, page_end)
    page_labels = [f"Trang {i}" for i in range(page_start, page_end + 1)]
else:
    image = Image.open(uploaded).convert("RGB")
    img_rgb = np.array(image)
    pages_bgr = [cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)]
    page_labels = ["Ảnh"]

# preview trước khi OCR
if len(pages_bgr) == 1:
    img_bgr = pages_bgr[0]
    processed_bgr = preprocess(img_bgr, preprocess_mode)
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Ảnh gốc")
        st.image(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB), use_container_width=True)
    with col2:
        st.subheader(f"Sau {preprocess_mode}")
        st.image(cv2.cvtColor(processed_bgr, cv2.COLOR_BGR2RGB), use_container_width=True)
else:
    with st.expander(f"Xem trước {len(pages_bgr)} trang"):
        prev_tabs = st.tabs(page_labels)
        for tab, p_bgr in zip(prev_tabs, pages_bgr):
            with tab:
                st.image(cv2.cvtColor(p_bgr, cv2.COLOR_BGR2RGB), use_container_width=True)

if st.button("Trích xuất văn bản", type="primary", use_container_width=True):
    reader = load_reader(languages)
    page_results = []
    progress = st.progress(0.0, text="Bắt đầu...")
    t_total = time.perf_counter()

    for idx, (label, img_bgr) in enumerate(zip(page_labels, pages_bgr)):
        progress.progress(idx / len(pages_bgr), text=f"Đang xử lý {label}...")
        processed_bgr = preprocess(img_bgr, preprocess_mode)
        t0 = time.perf_counter()
        results = reader.readtext(processed_bgr)
        elapsed = time.perf_counter() - t0
        filtered = [(b, t, c) for b, t, c in results if c >= conf_threshold]
        lines = group_by_lines(filtered)
        page_results.append({
            "label": label,
            "img_bgr": img_bgr,
            "processed_bgr": processed_bgr,
            "results": results,
            "filtered": filtered,
            "lines": lines,
            "sorted_items": [item for ln in lines for item in ln],
            "elapsed": elapsed,
        })
    progress.progress(1.0, text="Xong")
    total_time = time.perf_counter() - t_total

    n_regions = sum(len(p["filtered"]) for p in page_results)
    n_lines = sum(len(p["lines"]) for p in page_results)
    st.success(
        f"Đã đọc {n_regions} vùng / {n_lines} dòng qua {len(page_results)} trang "
        f"trong {total_time:.2f}s"
    )

    # gộp text các trang lại, có marker để biết trang nào
    parts = []
    for p in page_results:
        page_text = "\n".join(" ".join(text for _, text, _ in ln) for ln in p["lines"])
        if len(page_results) > 1:
            parts.append(f"--- {p['label']} ---\n{page_text}")
        else:
            parts.append(page_text)
    combined_text = "\n\n".join(parts)

    st.download_button(
        "Tải toàn bộ kết quả (.txt)",
        data=combined_text.encode("utf-8"),
        file_name=f"{file_stem}_ocr.txt",
        mime="text/plain",
        use_container_width=True,
    )

    if len(page_results) > 1:
        result_tabs = st.tabs([p["label"] for p in page_results])
        for tab, p in zip(result_tabs, page_results):
            with tab:
                render_page_result(p, file_stem)
    else:
        render_page_result(page_results[0], file_stem)
