from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np
from dotenv import load_dotenv
from paddleocr import PaddleOCR
from PIL import Image
from vietocr.tool.config import Cfg
from vietocr.tool.predictor import Predictor

try:
    from .document_detector import extract_document_region
except ImportError:
    from document_detector import extract_document_region

try:
    import google.generativeai as genai
except Exception:
    genai = None


BASE_DIR = Path(__file__).resolve().parent
VIETOCR_WEIGHTS = BASE_DIR / "weights" / "vgg_transformer.pth"

# PaddleOCR is kept for text-line detection. The YOLO model only prepares the
# camera image by finding the document region first.
paddle_ocr = PaddleOCR(
    lang="vi",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
)

config = Cfg.load_config_from_name("vgg_transformer")
config["device"] = os.getenv("OCR_DEVICE", "cpu")
config["weights"] = str(VIETOCR_WEIGHTS)
vietocr_model = Predictor(config)

load_dotenv(BASE_DIR / ".env")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if genai and GEMINI_API_KEY and GEMINI_API_KEY != "your_api_key_here":
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel("gemini-2.5-flash")
else:
    gemini_model = None


def correct_text_with_gemini(text: str) -> str:
    """Correct OCR spelling without changing the content."""
    if not gemini_model or not text.strip():
        return text

    try:
        prompt = f"""
Bạn là một chuyên gia sửa lỗi chính tả văn bản tiếng Việt.
Dưới đây là đoạn văn bản được quét bằng OCR. Nó có thể chứa lỗi do AI nhìn nhầm dấu, chữ hoặc khoảng trắng.

Yêu cầu:
1. Không thêm, bớt, bịa đặt, tóm tắt hoặc diễn giải nội dung.
2. Chỉ trả về văn bản sau khi sửa, không giải thích.
3. Giữ nguyên dấu chấm và xuống dòng giữa các đoạn để hệ thống đọc thành tiếng có nhịp nghỉ tự nhiên.

Văn bản thô:
{text}
"""
        response = gemini_model.generate_content(prompt)
        if response.text:
            return response.text.strip()
    except Exception as exc:
        print(f"Gemini API Error: {exc}")

    return text


def process_image(image_path: str) -> str:
    source_path = Path(image_path)
    source_image = cv2.imread(str(source_path))
    if source_image is None:
        return "Không đọc được ảnh."

    document_image, detection_info = extract_document_region(source_image)
    candidate_paths: list[Path] = []
    cleanup_paths: list[Path] = []

    if detection_info.get("status") == "detected":
        document_path = _write_temp_document_image(source_path, document_image)
        if document_path:
            candidate_paths.append(document_path)
            cleanup_paths.append(document_path)

    # Fallback keeps recall high when the segmentation model misses or crops too tightly.
    candidate_paths.append(source_path)

    try:
        for candidate_path in candidate_paths:
            raw_text = _recognize_text(candidate_path)
            if raw_text:
                return correct_text_with_gemini(raw_text)
    finally:
        for path in cleanup_paths:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

    return "Không tìm thấy văn bản."


def _write_temp_document_image(source_path: Path, image: np.ndarray) -> Path | None:
    output_path = source_path.with_name(f"{source_path.stem}_document{source_path.suffix}")
    try:
        if cv2.imwrite(str(output_path), image):
            return output_path
    except Exception as exc:
        print(f"Cannot write document crop: {exc}")
    return None


def _recognize_text(image_path: Path) -> str:
    boxes = _detect_text_boxes(image_path)
    if not boxes:
        return ""

    boxes = _xy_cut_sort(boxes)
    image = cv2.imread(str(image_path))
    if image is None:
        return ""

    texts: list[str] = []
    prev_box = None

    for box in boxes:
        crop = _crop_text_line(image, box)
        if crop is None or crop.size == 0:
            continue

        pil_image = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        text = vietocr_model.predict(pil_image)
        if not text or not text.strip():
            continue

        text = text.strip()
        if prev_box is not None:
            texts.append(_separator_between(prev_box, box))

        texts.append(text)
        prev_box = box

    return "".join(texts).strip()


def _detect_text_boxes(image_path: Path) -> list[list[list[float]]]:
    results = paddle_ocr.ocr(str(image_path), cls=False)
    boxes: list[list[list[float]]] = []

    for item in _iter_ocr_items(results):
        if isinstance(item, dict):
            polys = item.get("dt_polys")
            if polys is None:
                polys = item.get("rec_polys")
            if polys is not None:
                boxes.extend(_normalize_polys(polys))
            continue

        if not isinstance(item, (list, tuple)):
            continue

        # Old PaddleOCR format: [box, ("text", score)].
        if (
            len(item) == 2
            and isinstance(item[1], (tuple, list))
            and len(item[1]) >= 2
            and isinstance(item[1][0], str)
        ):
            boxes.append(_normalize_box(item[0]))
            continue

        # Detection-only format: [[x1, y1], [x2, y2], ...].
        if len(item) == 4 and isinstance(item[0], (list, tuple, np.ndarray)):
            boxes.append(_normalize_box(item))

    return [box for box in boxes if len(box) >= 4]


def _iter_ocr_items(results):
    if not results:
        return

    if isinstance(results, dict):
        yield results
        return

    for page in results:
        if isinstance(page, dict):
            yield page
        elif isinstance(page, (list, tuple)):
            for item in page:
                yield item


def _normalize_polys(polys) -> list[list[list[float]]]:
    normalized = []
    for poly in polys:
        box = _normalize_box(poly)
        if len(box) >= 4:
            normalized.append(box)
    return normalized


def _normalize_box(box) -> list[list[float]]:
    array = np.asarray(box, dtype=np.float32).reshape(-1, 2)
    return array.tolist()


def _xy_cut_sort(box_list: list[list[list[float]]]) -> list[list[list[float]]]:
    if not box_list:
        return []

    rects = []
    for box in box_list:
        xs = [point[0] for point in box]
        ys = [point[1] for point in box]
        rects.append(
            {
                "box": box,
                "xmin": min(xs),
                "xmax": max(xs),
                "ymin": min(ys),
                "ymax": max(ys),
            }
        )

    return _recursive_xy_cut(rects)


def _recursive_xy_cut(rects: list[dict]) -> list[list[list[float]]]:
    if not rects:
        return []
    if len(rects) == 1:
        return [rects[0]["box"]]

    rects = sorted(rects, key=lambda item: item["xmin"])
    x_gaps = []
    max_xmax = rects[0]["xmax"]
    for index in range(1, len(rects)):
        gap = rects[index]["xmin"] - max_xmax
        if gap > -5:
            x_gaps.append((gap, index))
        max_xmax = max(max_xmax, rects[index]["xmax"])

    if x_gaps:
        _, cut_index = max(x_gaps, key=lambda item: item[0])
        return _recursive_xy_cut(rects[:cut_index]) + _recursive_xy_cut(rects[cut_index:])

    rects = sorted(rects, key=lambda item: item["ymin"])
    y_gaps = []
    max_ymax = rects[0]["ymax"]
    for index in range(1, len(rects)):
        gap = rects[index]["ymin"] - max_ymax
        if gap > -5:
            y_gaps.append((gap, index))
        max_ymax = max(max_ymax, rects[index]["ymax"])

    if y_gaps:
        _, cut_index = max(y_gaps, key=lambda item: item[0])
        return _recursive_xy_cut(rects[:cut_index]) + _recursive_xy_cut(rects[cut_index:])

    rects = sorted(rects, key=lambda item: (item["ymin"], item["xmin"]))
    return [rect["box"] for rect in rects]


def _crop_text_line(image: np.ndarray, box: list[list[float]]) -> np.ndarray | None:
    points = np.asarray(box, dtype=np.int32)
    x, y, width, height = cv2.boundingRect(points)

    pad_y = int(height * 0.15)
    pad_x = int(width * 0.02)

    y1 = max(0, y - pad_y)
    y2 = min(image.shape[0], y + height + pad_y)
    x1 = max(0, x - pad_x)
    x2 = min(image.shape[1], x + width + pad_x)

    if x2 <= x1 or y2 <= y1:
        return None

    return image[y1:y2, x1:x2]


def _separator_between(prev_box: list[list[float]], current_box: list[list[float]]) -> str:
    prev_xs = [point[0] for point in prev_box]
    prev_ys = [point[1] for point in prev_box]
    current_xs = [point[0] for point in current_box]
    current_ys = [point[1] for point in current_box]

    prev_xmin = min(prev_xs)
    prev_ymin = min(prev_ys)
    prev_ymax = max(prev_ys)
    current_xmin = min(current_xs)
    current_ymin = min(current_ys)

    line_height = max(1, prev_ymax - prev_ymin)
    y_gap = current_ymin - prev_ymax
    x_jump = abs(current_xmin - prev_xmin)
    jumped_up = current_ymin < prev_ymin - line_height * 0.5

    if y_gap > line_height * 0.5 or jumped_up or x_jump > line_height * 4:
        return ".\n\n"

    return " "
