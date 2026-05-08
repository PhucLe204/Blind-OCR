import os
from dotenv import load_dotenv
import google.generativeai as genai

# pyrefly: ignore [missing-import]
import cv2
# pyrefly: ignore [missing-import]
import numpy as np
# pyrefly: ignore [missing-import]
from paddleocr import PaddleOCR
# pyrefly: ignore [missing-import]
from PIL import Image
# pyrefly: ignore [missing-import]
from vietocr.tool.predictor import Predictor
# pyrefly: ignore [missing-import]
from vietocr.tool.config import Cfg

# Khởi tạo PaddleOCR v3 (chỉ dùng để detection, bỏ các tham số cũ không còn hỗ trợ)
paddle_ocr = PaddleOCR(lang='vi', use_doc_orientation_classify=False, use_doc_unwarping=False)

# Cấu hình VietOCR để nhận diện chữ Việt chính xác hơn
config = Cfg.load_config_from_name('vgg_transformer')
config['device'] = 'cpu'
config['weights'] = 'weights/vgg_transformer.pth'
vietocr_model = Predictor(config)
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY and GEMINI_API_KEY != "your_api_key_here":
    genai.configure(api_key=GEMINI_API_KEY)
    # Sử dụng model nhanh và rẻ nhất hiện có
    gemini_model = genai.GenerativeModel('gemini-2.5-flash')
else:
    gemini_model = None

def correct_text_with_gemini(text: str) -> str:
    """Gửi toàn bộ văn bản cho Gemini để sửa lỗi chính tả theo ngữ cảnh."""
    if not gemini_model or not text.strip():
        return text
    try:
        prompt = f"""
Bạn là một chuyên gia sửa lỗi chính tả văn bản tiếng Việt.
Dưới đây là một đoạn văn bản được quét bằng công nghệ OCR. Nó có thể chứa các lỗi chính tả do AI nhìn nhầm dấu (ví dụ: 'đề đề xuất' thay vì 'để đề xuất', 'hiên có' thay vì 'hiện có').
Các đoạn văn bản, bài báo hoặc các khối thông tin riêng biệt đã được hệ thống phân tách bằng dấu chấm và dấu xuống dòng (.\n\n).
Hãy sửa lại các lỗi chính tả cho chuẩn xác dựa theo ngữ cảnh câu.
YÊU CẦU QUAN TRỌNG:
1. TUYỆT ĐỐI KHÔNG tự ý thêm, bớt, bịa đặt hay tóm tắt nội dung.
2. KHÔNG trả lời hay giải thích, CHỈ in ra văn bản sau khi đã sửa.
3. BẮT BUỘC PHẢI GIỮ NGUYÊN các dấu chấm (.) và dấu xuống dòng (\n\n) ở cuối mỗi đoạn để hệ thống phát âm (gTTS) có thể ngắt nhịp nghỉ dài hợp lý cho người khiếm thị.

Văn bản thô:
{text}
"""
        response = gemini_model.generate_content(prompt)
        if response.text:
            return response.text.strip()
    except Exception as e:
        print(f"Gemini API Error: {e}")
    return text

def process_image(image_path: str) -> str:
    # 1. Dùng PaddleOCR để tìm vị trí các dòng chữ
    results = paddle_ocr.ocr(image_path, cls=False)
    
    if not results or not results[0]:
        return "Không tìm thấy văn bản."

    page_result = results[0]
    boxes = []
    
    # PaddleOCR trả về mảng kết quả, ta lấy phần tọa độ (bounding box)
    for item in page_result:
        # Cấu trúc: [ [[x1, y1], [x2, y2], ...], ('text', score) ]
        if isinstance(item, list) and len(item) == 2 and isinstance(item[1], tuple):
            boxes.append(item[0])
        # Nếu chỉ detect, cấu trúc: [[x1, y1], [x2, y2], ...]
        elif isinstance(item, list) and len(item) == 4 and isinstance(item[0], list):
            boxes.append(item)

    if not boxes:
        return "Không tìm thấy văn bản."

    # 2. Sử dụng thuật toán XY-Cut để phân tích bố cục đa cột
    def xy_cut_sort(box_list):
        if not box_list:
            return []
        
        rects = []
        for b in box_list:
            xs = [pt[0] for pt in b]
            ys = [pt[1] for pt in b]
            rects.append({
                'box': b,
                'xmin': min(xs),
                'xmax': max(xs),
                'ymin': min(ys),
                'ymax': max(ys)
            })
            
        def recursive_xy_cut(current_rects):
            if not current_rects:
                return []
            if len(current_rects) == 1:
                return [current_rects[0]['box']]
                
            # ƯU TIÊN 1: Cố gắng cắt dọc (X-Cut) để chia cột báo
            current_rects.sort(key=lambda r: r['xmin'])
            x_gaps = []
            max_xmax = current_rects[0]['xmax']
            for i in range(1, len(current_rects)):
                gap = current_rects[i]['xmin'] - max_xmax
                if gap > -5: # Tolerance
                    x_gaps.append((gap, i))
                max_xmax = max(max_xmax, current_rects[i]['xmax'])
                
            if x_gaps:
                x_gaps.sort(key=lambda g: g[0], reverse=True)
                cut_index = x_gaps[0][1]
                return recursive_xy_cut(current_rects[:cut_index]) + recursive_xy_cut(current_rects[cut_index:])

            # ƯU TIÊN 2: Nếu không cắt dọc được, cố gắng cắt ngang (Y-Cut) để chia hàng/block
            current_rects.sort(key=lambda r: r['ymin'])
            y_gaps = []
            max_ymax = current_rects[0]['ymax']
            for i in range(1, len(current_rects)):
                gap = current_rects[i]['ymin'] - max_ymax
                if gap > -5: 
                    y_gaps.append((gap, i))
                max_ymax = max(max_ymax, current_rects[i]['ymax'])
                
            if y_gaps:
                y_gaps.sort(key=lambda g: g[0], reverse=True)
                cut_index = y_gaps[0][1]
                return recursive_xy_cut(current_rects[:cut_index]) + recursive_xy_cut(current_rects[cut_index:])
                
            # Fallback nếu các box hoàn toàn dính lẹo vào nhau
            current_rects.sort(key=lambda r: (r['ymin'], r['xmin']))
            return [r['box'] for r in current_rects]

        return recursive_xy_cut(rects)

    boxes = xy_cut_sort(boxes)

    # 3. Cắt từng dòng và nhận diện bằng VietOCR
    img = cv2.imread(image_path)
    texts = []
    prev_box = None

    for box in boxes:
        pts = np.array(box, dtype=np.int32)
        x, y, w, h = cv2.boundingRect(pts)
        
        # Thêm padding (mở rộng vùng cắt) để không cắt mất dấu tiếng Việt ở trên/dưới
        pad_y = int(h * 0.15)  # Mở rộng 15% chiều cao lên trên và xuống dưới
        pad_x = int(w * 0.02)  # Mở rộng một chút chiều ngang
        
        y1 = max(0, y - pad_y)
        y2 = min(img.shape[0], y + h + pad_y)
        x1 = max(0, x - pad_x)
        x2 = min(img.shape[1], x + w + pad_x)

        crop = img[y1:y2, x1:x2]
        
        if crop.size > 0:
            pil_img = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
            text = vietocr_model.predict(pil_img)
            if text and text.strip():
                text = text.strip()
                if prev_box is not None:
                    # Tính khoảng cách so với box liền trước để phát hiện chuyển đoạn/cột
                    pxs = [pt[0] for pt in prev_box]
                    pys = [pt[1] for pt in prev_box]
                    p_xmin, p_ymin = min(pxs), min(pys)
                    p_ymax = max(pys)
                    line_height = max(1, p_ymax - p_ymin)
                    
                    y_gap = y - p_ymax
                    x_jump = abs(x - p_xmin)
                    jumped_up = y < p_ymin - line_height * 0.5 # Nếu đọc ngược lên trên -> chắc chắn là sang cột mới
                    
                    # Nếu cách nhau quá xa theo trục Y (đoạn mới), hoặc nhảy ngược lên trên (cột mới), hoặc cách nhau cực xa trục X
                    if y_gap > line_height * 0.5 or jumped_up or x_jump > line_height * 4:
                        texts.append(".\n\n") # Thêm dấu chấm và xuống dòng để gTTS ngắt nghỉ dài
                    else:
                        texts.append(" ") # Cùng một đoạn thì cách nhau 1 khoảng trắng
                
                texts.append(text)
                prev_box = box

    final_text = "".join(texts)
    
    if final_text:
        # Xử lý hậu kỳ toàn bộ văn bản một lần duy nhất bằng Gemini
        corrected_text = correct_text_with_gemini(final_text)
        return corrected_text
    else:
        return "Không tìm thấy văn bản."