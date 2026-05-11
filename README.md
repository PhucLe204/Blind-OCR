# Blind-OCR: Hệ Thống Hỗ Trợ Đọc Tài Liệu Cho Người Khiếm Thị

Blind-OCR là một hệ thống hỗ trợ người khiếm thị tiếp cận tài liệu in ấn bằng cách sử dụng Trí tuệ nhân tạo (AI) để hướng dẫn căn chỉnh camera và nhận diện văn bản tiếng Việt với độ chính xác cao.

---

## 🚀 Tính Năng Chính

- **Hướng dẫn giọng nói thời gian thực**: Điều hướng tay người dùng (trái, phải, lên, xuống) để tài liệu nằm giữa khung hình.
- **Tự động chụp ảnh**: AI tự động chụp khi ảnh đủ nét và cân đối.
- **Hybrid Mode**: Dùng điện thoại làm máy quét (Scanner) và máy tính làm bộ đọc (Reader).
- **Sửa lỗi bằng Gemini AI**: Tự động sửa lỗi chính tả và mượt hóa văn bản sau khi quét.

---

## 🛠 Yêu Cầu Hệ Thống

- **Python**: 3.9 trở lên.
- **Node.js**: 16.x trở lên.
- **Camera**: Webcam máy tính hoặc Camera điện thoại.
- **API Key**: Cần có `GEMINI_API_KEY` từ Google AI Studio.

---

## 📦 Cài Đặt

### 1. Backend (Python)
```bash
cd backend
python -m venv venv
# Trên Windows dùng:
.\venv\Scripts\activate
# Cài đặt thư viện:
pip install -r requirements.txt
```
*Tạo file `.env` trong thư mục `backend` và thêm vào:*
```env
GEMINI_API_KEY=your_api_key_here
```

### 2. Frontend (React)
```bash
cd frontend
npm install
```

---

## 🏃 Hướng Dẫn Chạy

### Bước 1: Khởi động Backend
```bash
cd backend
python main.py
```
Server sẽ chạy mặc định tại: `http://localhost:8000`

### Bước 2: Khởi động Frontend
```bash
cd frontend
npm run dev
```
Truy cập: `http://localhost:5173`

---

## 📖 Hướng Dẫn Sử Dụng

### 1. Chế độ Quét (Scanner - Trên Điện Thoại)
- Truy cập trình duyệt điện thoại qua địa chỉ IP máy tính: `http://<ip-cua-may-tinh>:5173?mode=scanner`.
- **Lưu ý**: Chức năng Camera yêu cầu HTTPS. Bạn nên dùng `ngrok` hoặc cấu hình HTTPS cho Vite để dùng trên điện thoại.
- Chạm vào màn hình để bắt đầu. Nghe theo chỉ dẫn giọng nói.

### 2. Chế độ Đọc (Reader - Trên Máy Tính)
- Truy cập: `http://localhost:5173?mode=reader`.
- Máy tính sẽ tự động đọc kết quả khi điện thoại quét xong.

### 3. Phím tắt
- **Phím Enter**: Bật camera / Chụp ảnh.
- **Phím Space**: Tạm dừng hoặc tiếp tục đọc âm thanh kết quả.

---

## 🏗 Công Nghệ Sử Dụng

- **AI Models**: YOLOv8-seg, PaddleOCR, VietOCR, Gemini 2.5 Flash.
- **Backend**: FastAPI, gTTS.
- **Frontend**: React + Vite, Axios.
- **Xử lý ảnh**: OpenCV, NumPy.

---

## 📧 Liên Hệ
Nếu bạn gặp khó khăn trong quá trình cài đặt hoặc sử dụng, vui lòng liên hệ đội ngũ phát triển.
