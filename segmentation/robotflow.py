import cv2
import time
import os
import numpy as np
from ultralytics import YOLO
import tkinter as tk
from tkinter import filedialog

# =================================================== #
#                 HỘP THOẠI CHỌN FILE                 #
# =================================================== #
# Ẩn cửa sổ gốc của Tkinter (chỉ giữ lại hộp thoại chọn file)
root = tk.Tk()
root.withdraw() 

print("📁 Vui lòng chọn file video từ cửa sổ vừa hiện lên...")
VIDEO_PATH = filedialog.askopenfilename(
    title="Chọn video để quét tài liệu",
    filetypes=[
        ("Video Files", "*.mp4 *.avi *.mov *.mkv"), 
        ("All Files", "*.*")
    ]
)

# Kiểm tra xem người dùng có bấm "Cancel" không
if not VIDEO_PATH:
    print("❌ Bạn chưa chọn video nào. Đang thoát chương trình...")
    exit()

print(f"✅ Đã chọn video: {VIDEO_PATH}")

# =================================================== #
# -------------------- CẤU HÌNH --------------------- #
MODEL_PATH = "best.pt"             # Đường dẫn file model
SAVE_DIR = "captured_docs"         # Thư mục lưu ảnh chụp

CENTER_TOLERANCE = 80              # Bán kính vùng tâm (pixels)
HOLD_TIME = 2.0                    # Thời gian yêu cầu giữ tĩnh (giây)
BLUR_THRESHOLD = 80.0              # Ngưỡng phát hiện mờ

# Tạo thư mục lưu ảnh nếu chưa có
os.makedirs(SAVE_DIR, exist_ok=True)

# Load model YOLOv11
print("🧠 Đang tải model AI...")
model = YOLO(MODEL_PATH)

# Mở luồng video từ file vừa chọn
cap = cv2.VideoCapture(VIDEO_PATH)

# Biến trạng thái đếm thời gian
center_start_time = None
captured = False

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        print("🎬 Đã phát hết video.")
        break

    # Lấy kích thước khung hình
    H, W = frame.shape[:2]
    frame_cx, frame_cy = W // 2, H // 2  # Tọa độ tâm màn hình

    # Chạy YOLO dự đoán (Ép size=416 cho laptop chạy mượt hơn)
    results = model(frame, verbose=False, imgsz=416)
    
    # Lấy ảnh đã được YOLO vẽ sẵn khung và mặt nạ
    annotated_frame = results[0].plot()

    # Vẽ vòng tròn tâm ngắm trên màn hình
    cv2.circle(annotated_frame, (frame_cx, frame_cy), CENTER_TOLERANCE, (255, 255, 0), 2)
    cv2.circle(annotated_frame, (frame_cx, frame_cy), 2, (0, 0, 255), -1)

    boxes = results[0].boxes
    message = ""
    color = (0, 0, 255) # Đỏ mặc định

    if len(boxes) > 0:
        # Lấy tọa độ bounding box của tài liệu
        box = boxes[0].xyxy[0].cpu().numpy()
        x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
        
        # Tính tâm của tài liệu
        doc_cx = (x1 + x2) // 2
        doc_cy = (y1 + y2) // 2

        # Vẽ một điểm báo tâm của tài liệu
        cv2.circle(annotated_frame, (doc_cx, doc_cy), 5, (0, 255, 0), -1)
        cv2.line(annotated_frame, (frame_cx, frame_cy), (doc_cx, doc_cy), (255, 255, 255), 1)

        # Tính toán độ mờ/rung của khung hình
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur_val = cv2.Laplacian(gray, cv2.CV_64F).var()

        if blur_val < BLUR_THRESHOLD:
            message = f"ANH MO ({blur_val:.0f}) - HAY GIU YEN!"
            center_start_time = None
        else:
            dx = doc_cx - frame_cx
            dy = doc_cy - frame_cy

            if abs(dx) <= CENTER_TOLERANCE and abs(dy) <= CENTER_TOLERANCE:
                color = (0, 255, 0) # Xanh lá
                if center_start_time is None:
                    center_start_time = time.time()
                    captured = False
                
                elapsed = time.time() - center_start_time
                message = f"GIU NGUYEN... {HOLD_TIME - elapsed:.1f}s"

                cv2.circle(annotated_frame, (frame_cx, frame_cy), CENTER_TOLERANCE, (0, 255, 0), 2)

                if elapsed >= HOLD_TIME and not captured:
                    filename = os.path.join(SAVE_DIR, f"scan_{int(time.time())}.jpg")
                    cv2.imwrite(filename, frame) 
                    print(f"📸 ĐÃ CHỤP ẢNH: {filename}")
                    captured = True
                    message = "DA CHUP THANH CONG!"
                    color = (255, 0, 255)
            else:
                center_start_time = None
                captured = False
                
                # Điều hướng
                if dx > CENTER_TOLERANCE:
                    message = "<-- DUA MAY SANG PHAI"
                elif dx < -CENTER_TOLERANCE:
                    message = "DUA MAY SANG TRAI -->"
                elif dy > CENTER_TOLERANCE:
                    message = "DUA MAY XUONG DUOI vv"
                elif dy < -CENTER_TOLERANCE:
                    message = "DUA MAY LEN TREN ^^"
    else:
        center_start_time = None
        message = "KHONG THAY TAI LIEU"
        color = (100, 100, 100)

    # Hiển thị thông báo
    cv2.putText(annotated_frame, message, (50, 80), cv2.FONT_HERSHEY_DUPLEX, 1.2, color, 3)

    # Hiển thị video
    cv2.imshow("Smart Document Scanner", annotated_frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()