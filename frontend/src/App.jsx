import { useEffect, useRef, useState } from 'react';
import axios from 'axios';

const backendCandidates = [
  import.meta.env.VITE_BACKEND_URL,
  `http://${window.location.hostname}:8010`,
  `http://${window.location.hostname}:8000`,
  'http://127.0.0.1:8010',
  'http://127.0.0.1:8000',
].filter(Boolean);

function App() {
  const [status, setStatus] = useState('Sẵn sàng. Bật camera để chụp tài liệu hoặc chọn ảnh có sẵn.');
  const [isLoading, setIsLoading] = useState(false);
  const [isCameraOn, setIsCameraOn] = useState(false);
  const [cameraError, setCameraError] = useState('');

  const audioRef = useRef(null);
  const canvasRef = useRef(null);
  const fileInputRef = useRef(null);
  const videoRef = useRef(null);
  const streamRef = useRef(null);

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        if (isCameraOn) {
          captureCameraImage();
        } else {
          startCamera();
        }
      }

      if (event.code === 'Space') {
        event.preventDefault();
        if (audioRef.current) {
          audioRef.current.paused ? audioRef.current.play() : audioRef.current.pause();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isCameraOn, isLoading]);

  useEffect(() => {
    return () => stopCamera();
  }, []);

  const startCamera = async () => {
    if (isLoading || isCameraOn) return;

    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError('Trình duyệt không hỗ trợ camera trực tiếp. Hãy dùng nút chọn ảnh/camera.');
      fileInputRef.current?.click();
      return;
    }

    try {
      setCameraError('');
      setStatus('Đang mở camera...');
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      });

      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }

      setIsCameraOn(true);
      setStatus('Camera đã bật. Đưa tài liệu vào khung rồi bấm Chụp và đọc.');
    } catch (error) {
      console.error(error);
      setCameraError('Không mở được camera. Kiểm tra quyền camera hoặc dùng nút chọn ảnh/camera.');
      setStatus('Không mở được camera.');
    }
  };

  const stopCamera = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }

    setIsCameraOn(false);
  };

  const captureCameraImage = async () => {
    if (isLoading || !videoRef.current || !canvasRef.current) return;

    const video = videoRef.current;
    if (!video.videoWidth || !video.videoHeight) {
      setStatus('Camera chưa sẵn sàng, thử chụp lại sau một giây.');
      return;
    }

    const canvas = canvasRef.current;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const context = canvas.getContext('2d');
    context.drawImage(video, 0, 0, canvas.width, canvas.height);

    canvas.toBlob(
      async (blob) => {
        if (!blob) {
          setStatus('Không chụp được ảnh từ camera.');
          return;
        }

        const file = new File([blob], `camera-${Date.now()}.jpg`, { type: 'image/jpeg' });
        await sendImageToBackend(file);
      },
      'image/jpeg',
      0.92,
    );
  };

  const handleFileChange = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    await sendImageToBackend(file);
    event.target.value = null;
  };

  const sendImageToBackend = async (file) => {
    setStatus('Đang gửi tài liệu cho AI đọc, vui lòng chờ...');
    setIsLoading(true);

    try {
      const { response, backendBaseUrl } = await uploadWithFallback(file);

      if (response.data.audio_url) {
        setStatus(`Đã xử lý xong. Nội dung: ${response.data.text}`);
        audioRef.current.src = backendBaseUrl + response.data.audio_url;
        await audioRef.current.play();
      } else {
        setStatus('Không tìm thấy văn bản trong ảnh.');
      }
    } catch (error) {
      console.error(error);
      setStatus(
        'Lỗi kết nối máy chủ AI. Backend cần chạy ở port 8010 hoặc 8000, ví dụ: python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000',
      );
    } finally {
      setIsLoading(false);
    }
  };

  const uploadWithFallback = async (file) => {
    let lastError;

    for (const backendBaseUrl of uniqueUrls(backendCandidates)) {
      try {
        const formData = new FormData();
        formData.append('file', file);

        const response = await axios.post(`${backendBaseUrl}/upload`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: 120000,
        });

        return { response, backendBaseUrl };
      } catch (error) {
        lastError = error;
      }
    }

    throw lastError;
  };

  return (
    <main className="app-shell">
      <div aria-live="polite" className="sr-only">
        {status}
      </div>

      <section className="reader-panel">
        <div className="reader-header">
          <h1>Đọc tài liệu</h1>
          <p className={isLoading ? 'state busy' : 'state ready'}>
            {isLoading ? 'Đang chạy AI' : isCameraOn ? 'Camera đang bật' : 'Sẵn sàng'}
          </p>
        </div>

        <div className="camera-stage">
          <video ref={videoRef} className="camera-view" playsInline muted />
          {!isCameraOn && (
            <div className="camera-placeholder">
              <span>Camera chưa bật</span>
            </div>
          )}
        </div>

        {cameraError && <p className="error-text">{cameraError}</p>}

        <div className="actions">
          <button type="button" onClick={startCamera} disabled={isLoading || isCameraOn}>
            Bật camera
          </button>
          <button type="button" onClick={captureCameraImage} disabled={isLoading || !isCameraOn}>
            Chụp và đọc
          </button>
          <button type="button" onClick={stopCamera} disabled={isLoading || !isCameraOn}>
            Tắt camera
          </button>
          <button type="button" onClick={() => fileInputRef.current?.click()} disabled={isLoading}>
            Chọn ảnh
          </button>
        </div>

        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          onChange={handleFileChange}
          className="hidden-input"
        />
        <canvas ref={canvasRef} className="hidden-input" />

        <div className="status-box">
          <p>{status}</p>
        </div>

        <audio ref={audioRef} controls className="audio-player" />

        <div className="shortcut-box">
          <p>
            <strong>Enter</strong>: bật camera hoặc chụp khi camera đang bật
          </p>
          <p>
            <strong>Space</strong>: dừng/phát âm thanh
          </p>
        </div>
      </section>
    </main>
  );
}

export default App;

function uniqueUrls(urls) {
  return [...new Set(urls.map((url) => url.replace(/\/$/, '')))];
}
