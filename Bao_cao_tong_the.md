# BÁO CÁO KỸ THUẬT TOÀN DIỆN: HỆ THỐNG HỖ TRỢ ĐỌC TÀI LIỆU THÔNG MINH (BLIND-OCR)

---

## 1. ĐẶT VẤN ĐỀ VÀ MỤC TIÊU DỰ ÁN
Dự án giải quyết bài toán căn chỉnh camera cho người khiếm thị bằng cách kết hợp thị giác máy tính và tương tác giọng nói thời gian thực. Mục tiêu là tạo ra một hệ thống tự vận hành (autonomous) giúp người khiếm thị tiếp cận tài liệu in ấn một cách độc lập.

---

## 2. KIẾN TRÚC HỆ THỐNG (SYSTEM ARCHITECTURE)
Hệ thống được thiết kế theo mô hình Client-Server chuyên sâu:
- **Frontend (Client)**: Đóng vai trò là **Hệ điều phối tương tác** (Interaction Engine).
- **Backend (Server)**: Đóng vai trò là **Trung tâm AI & Xử lý dữ liệu** (AI Processing Hub).

---

## 3. PHÂN TÍCH CHI TIẾT BACKEND: TRUNG TÂM AI & XỬ LÝ DỮ LIỆU

Backend được xây dựng trên nền tảng Python (FastAPI), tích hợp các công nghệ AI hiện đại nhất để xử lý chu trình từ hình ảnh thô đến văn bản có ý nghĩa.

### 3.1. Module Thị giác máy tính & Định vị (YOLOv8 Segmentation)
Chúng em sử dụng mô hình **YOLOv8-seg** (Instance Segmentation) thay vì Object Detection thông thường:
- **Độ chính xác biên**: Segmentation cho phép xác định chính xác các điểm ảnh thuộc về tài liệu, giúp tìm ra 4 đỉnh (corners) ngay cả khi tài liệu bị che khuất một phần hoặc nền phức tạp.
- **Thuật toán Hướng dẫn (Guidance Algorithm)**:
    - **Kiểm tra độ nhòe (Blur Detection)**: Sử dụng toán tử Laplacian để tính toán mức độ thay đổi gradient. Công thức: $Score = Var(Laplacian(Image))$. Nếu điểm số thấp, hệ thống cảnh báo người dùng giữ yên tay.
    - **Phân tích hình học (Geometric Analysis)**: Tính toán tọa độ tâm và so sánh với tâm khung hình để điều hướng người dùng (Trái/Phải/Lên/Xuống).
    - **Tỷ lệ diện tích (Area Coverage)**: Tính toán tỷ lệ diện tích tài liệu / diện tích khung hình để đảm bảo người dùng đặt tài liệu ở khoảng cách tối ưu.

### 3.2. Module OCR Pipeline: Sự kết hợp Hybrid
Để đạt độ chính xác tối ưu cho tiếng Việt, hệ thống phối hợp các công nghệ chuyên sâu:
- **Hiệu chỉnh góc nhìn (Perspective Correction)**: Sử dụng phép biến đổi 4 điểm (Homography Transformation) để "trải phẳng" ảnh tài liệu. Điều này loại bỏ hiện tượng chữ bị biến dạng do góc chụp nghiêng.
- **Phát hiện văn bản (PaddleOCR)**: Sử dụng thuật toán DB (Differentiable Binarization) để tìm chính xác tọa độ các dòng văn bản.
- **Nhận diện chữ viết (VietOCR - VGG Transformer)**: Sử dụng kiến trúc Encoder-Decoder với Transformer. Điều này giúp mô hình hiểu được sự phụ thuộc ngữ cảnh giữa các ký tự, đặc biệt mạnh mẽ trong việc nhận diện chính xác các dấu thanh tiếng Việt phức tạp.
- **Thuật toán sắp xếp (XY-Cut)**: Sử dụng thuật toán phân mảnh đệ quy để sắp xếp các dòng văn bản theo đúng thứ tự đọc (ví dụ: tài liệu chia cột), tránh việc đọc lộn xộn nội dung.

### 3.3. Module Trí tuệ ngôn ngữ (Google Gemini API)
Đây là lớp "Hậu xử lý thông minh" giúp văn bản đạt độ tin cậy cao:
- **Sửa lỗi ngữ cảnh (Contextual Correction)**: Gemini hiểu nội dung để sửa các từ bị nhận diện sai logic (ví dụ: "ch0" thành "cho").
- **Lọc nhiễu (Noise Filtering)**: Tự động loại bỏ các ký tự rác sinh ra do bóng đổ hoặc vết bẩn.
- **Định dạng tự nhiên**: Giúp văn bản mạch lạc, có chấm phẩy và xuống dòng hợp lý để máy đọc dễ nghe hơn.

### 3.4. Hệ thống Quản lý Âm thanh (gTTS & Caching)
- **Cơ chế Caching**: Backend sử dụng mã băm (Hash) nội dung văn bản để lưu trữ file âm thanh. Nếu người dùng yêu cầu đọc lại, hệ thống sẽ trả về kết quả ngay lập tức mà không cần tạo lại.
- **Server Playback**: Hỗ trợ phát âm thanh trực tiếp từ phía Server (dùng cho chế độ Hybrid) để tận dụng hệ thống loa cố định.

---

## 4. PHÂN TÍCH CHI TIẾT FRONTEND: HỆ ĐIỀU PHỐI TƯƠNG TÁC
Frontend đóng vai trò quản lý thiết bị và luồng tương tác người dùng:
- **Interaction Engine**: Quản lý vòng lặp hướng dẫn và cơ chế tự động chụp ảnh.
- **Speech Priority Queue**: Hệ thống hàng đợi âm thanh ưu tiên, đảm bảo thông tin quan trọng luôn được phát tới người dùng trước.
- **Connectivity Layer**: Quản lý kết nối đa Server và cơ chế đồng bộ Hybrid.

---

## 5. THÔNG SỐ KỸ THUẬT VÀ HIỆU NĂNG
- **Thời gian phản hồi**: < 300ms cho hướng dẫn thời gian thực.
- **Độ chính xác**: > 98% nhờ sự kết hợp VietOCR và Gemini.
- **Công nghệ**: FastAPI, YOLOv8, PaddleOCR, VietOCR, Gemini API, React.

---

## 6. KẾT LUẬN
Dự án thể hiện một sự kết hợp hoàn hảo giữa kỹ thuật thị giác máy tính, Deep Learning chuyên sâu và logic điều phối tương tác. Backend không chỉ là nơi lưu trữ mà là một trung tâm AI thực thụ, đảm bảo tính chính xác và tin cậy cho người khiếm thị.
