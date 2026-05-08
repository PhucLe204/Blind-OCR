import { useState, useRef, useEffect } from 'react';
import axios from 'axios';

function App() {
  const [status, setStatus] = useState("Chào mừng. Bấm Enter để chọn ảnh hoặc chụp camera.");
  const [isLoading, setIsLoading] = useState(false);
  const audioRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Enter') fileInputRef.current.click();
      if (e.code === 'Space') {
        e.preventDefault();
        if (audioRef.current) {
          audioRef.current.paused ? audioRef.current.play() : audioRef.current.pause();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleFileChange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setStatus("Đang gửi tài liệu cho AI đọc, vui lòng chờ...");
    setIsLoading(true);

    const formData = new FormData();
    formData.append("file", file);

    try {
      // Lấy IP động của máy tính (host) để điện thoại không bị nhầm gửi vào localhost của chính nó
      const backendBaseUrl = `http://${window.location.hostname}:8000`;
      
      const response = await axios.post(`${backendBaseUrl}/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      if (response.data.audio_url) {
        setStatus("Đã xử lý xong. Hệ thống bắt đầu đọc. Nội dung: " + response.data.text);
        audioRef.current.src = backendBaseUrl + response.data.audio_url;
        audioRef.current.play();
      } else {
        setStatus("Không tìm thấy văn bản trong ảnh.");
      }
    } catch (error) {
      console.error(error);
      setStatus("Lỗi kết nối máy chủ AI. Hãy kiểm tra lại Backend.");
    } finally {
      setIsLoading(false);
      e.target.value = null; 
    }
  };

  return (
    <div style={{ padding: '20px', fontFamily: 'sans-serif', textAlign: 'center', maxWidth: '500px', margin: '0 auto' }}>
      
      <div aria-live="polite" style={{ position: 'absolute', left: '-9999px' }}>
        {status}
      </div>

      <h2 style={{ color: '#2563eb' }}>Đọc Báo Cho Người Khiếm Thị</h2>
      <p>Trạng thái: <b>{isLoading ? "⏳ Đang chạy AI..." : "✅ Sẵn sàng"}</b></p>

      <button 
        onClick={() => fileInputRef.current.click()} 
        disabled={isLoading}
        style={{ padding: '20px', fontSize: '20px', cursor: isLoading ? 'not-allowed' : 'pointer', width: '100%', backgroundColor: isLoading ? '#ccc' : '#2563eb', color: 'white', border: 'none', borderRadius: '10px' }}>
        📸 CHỌN ẢNH / CAMERA
      </button>
      <input type="file" accept="image/*" capture="environment" ref={fileInputRef} onChange={handleFileChange} style={{ display: 'none' }} />

      <div style={{ marginTop: '20px' }}>
        <audio ref={audioRef} controls style={{ width: '100%' }} />
      </div>

      <div style={{ marginTop: '30px', textAlign: 'left', backgroundColor: '#f3f4f6', padding: '15px', borderRadius: '8px' }}>
        <p style={{ margin: '0 0 10px 0' }}><b>Phím tắt:</b></p>
        <ul style={{ margin: 0, paddingLeft: '20px' }}>
          <li><b>Enter</b>: Chọn ảnh/Bật camera</li>
          <li><b>Space</b>: Dừng/Phát âm thanh</li>
        </ul>
      </div>
    </div>
  );
}

export default App;