import { useEffect, useRef, useState } from 'react';
import axios from 'axios';

const GUIDE_INTERVAL_MS = 1000;
const READY_CHECKS_BEFORE_CAPTURE = 2;
const GUIDE_REPEAT_DELAY_MS = 3000;
const READER_POLL_INTERVAL_MS = 1500;

const COMMON_GUIDE_MESSAGES = [
  'Camera đã bật. Đưa tài liệu vào trước camera.',
  'Chưa thấy tài liệu. Đưa tài liệu vào trước camera.',
  'Chưa thấy tài liệu rõ. Đưa tài liệu vào giữa camera.',
  'Đưa tài liệu sang trái.',
  'Đưa tài liệu sang phải.',
  'Đưa tài liệu lên trên.',
  'Đưa tài liệu xuống dưới.',
  'Đưa tài liệu lại gần camera hơn.',
  'Đưa tài liệu ra xa camera một chút.',
  'Ảnh đang mờ. Giữ yên tài liệu.',
  'Tài liệu đã rõ và nằm giữa khung. Giữ yên.',
  'Tài liệu đã rõ. Giữ yên, hệ thống sẽ chụp.',
  'Đang gửi tài liệu cho AI đọc, vui lòng chờ.',
  'Đã gửi tài liệu về máy tính để đọc.',
];

const backendCandidates = [
  `${window.location.origin}/api`,
  import.meta.env.VITE_BACKEND_URL,
  `http://${window.location.hostname}:8000`,
  'http://localhost:8000',
].filter(Boolean);

function App() {
  const appMode = getAppMode();
  const isRemoteScannerMode = appMode === 'scanner';
  const isComputerReaderMode = appMode === 'reader';
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);
  const [showScanner, setShowScanner] = useState(isMobile);
  const [status, setStatus] = useState('Sẵn sàng. Bật camera để bắt đầu.');
  const [guideMessage, setGuideMessage] = useState('Hệ thống sẽ hướng dẫn bằng giọng nói.');
  const [isLoading, setIsLoading] = useState(false);
  const [isCameraOn, setIsCameraOn] = useState(false);
  const [cameraError, setCameraError] = useState('');
  
  // Trạng thái cho việc nhận dữ liệu từ điện thoại
  const [readerStatus, setReaderStatus] = useState('Máy tính đang sẵn sàng nhận dữ liệu.');
  const [readerText, setReaderText] = useState('');
  const [isReaderListening, setIsReaderListening] = useState(true);

  const audioRef = useRef(null);
  const guideAudioRef = useRef(null);
  const canvasRef = useRef(null);
  const fileInputRef = useRef(null);
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const guideTimerRef = useRef(null);
  const guideInFlightRef = useRef(false);
  const guideAudioRequestIdRef = useRef(0);
  const guideAudioCacheRef = useRef(new Map());
  const guideAudioPendingRef = useRef(new Map());
  const isSpeakingRef = useRef(false);
  const speechQueueRef = useRef([]);
  const lastSpokenRef = useRef({ message: '', time: 0 });
  const readerLastIdRef = useRef('');
  const readerStartedAtRef = useRef(Date.now() / 1000 - 1);
  const activeBackendBaseUrlRef = useRef(null);
  const readyCountRef = useRef(0);
  const autoCaptureRef = useRef(false);
  const isLoadingRef = useRef(false);

  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth <= 768;
      setIsMobile(mobile);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    isLoadingRef.current = isLoading;
  }, [isLoading]);

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
          if (audioRef.current.paused) {
            audioRef.current.play().catch(() => {});
          } else {
            audioRef.current.pause();
          }
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isCameraOn]);

  useEffect(() => {
    if (isCameraOn && !isLoading) {
      startGuidanceLoop();
    } else {
      stopGuidanceLoop();
    }
    return () => stopGuidanceLoop();
  }, [isCameraOn, isLoading]);

  // Luôn lắng nghe dữ liệu từ điện thoại nếu là máy tính
  useEffect(() => {
    if (!isMobile && isReaderListening) {
      let cancelled = false;
      const poll = () => {
        pollLatestReading().catch(() => {
          if (!cancelled) setReaderStatus('Lỗi kết nối máy chủ.');
        });
      };
      poll();
      const timer = window.setInterval(poll, READER_POLL_INTERVAL_MS);
      return () => {
        cancelled = true;
        window.clearInterval(timer);
      };
    }
  }, [isMobile, isReaderListening]);

  useEffect(() => {
    return () => {
      stopGuidanceLoop();
      stopCamera();
    };
  }, []);

  async function speak(message, priority = false) {
    if (!message) return;
    if (priority) {
      speechQueueRef.current = [message];
      if (isSpeakingRef.current && guideAudioRef.current) {
        guideAudioRef.current.pause();
        isSpeakingRef.current = false;
      }
    } else {
      if (isSpeakingRef.current || speechQueueRef.current.includes(message)) return;
      const now = Date.now();
      if (lastSpokenRef.current.message === message && now - lastSpokenRef.current.time < GUIDE_REPEAT_DELAY_MS) {
        return;
      }
      speechQueueRef.current.push(message);
    }
    processQueue();
  }

  async function processQueue() {
    if (isSpeakingRef.current || speechQueueRef.current.length === 0) return;
    isSpeakingRef.current = true;
    const message = speechQueueRef.current.shift();
    lastSpokenRef.current = { message, time: Date.now() };
    try {
      const audioUrl = await cacheGuideAudio(message);
      if (!audioUrl) {
        isSpeakingRef.current = false;
        processQueue();
        return;
      }
      if (guideAudioRef.current) {
        guideAudioRef.current.src = audioUrl;
        guideAudioRef.current.onended = () => {
          isSpeakingRef.current = false;
          processQueue();
        };
        guideAudioRef.current.onerror = () => {
          isSpeakingRef.current = false;
          processQueue();
        };
        await guideAudioRef.current.play();
      }
    } catch (e) {
      isSpeakingRef.current = false;
      processQueue();
    }
  }

  async function cacheGuideAudio(message) {
    const cached = guideAudioCacheRef.current.get(message);
    if (cached) return cached;
    const pending = guideAudioPendingRef.current.get(message);
    if (pending) return pending;
    const request = postJsonWithFallback('/guide-audio', { text: message }, 10000)
      .then(({ response, backendBaseUrl }) => {
        const audioUrl = response.data?.audio_url ? backendBaseUrl + response.data.audio_url : '';
        if (audioUrl) {
          guideAudioCacheRef.current.set(message, audioUrl);
        }
        return audioUrl;
      })
      .finally(() => {
        guideAudioPendingRef.current.delete(message);
      });
    guideAudioPendingRef.current.set(message, request);
    return request;
  }

  function preloadGuideAudios() {
    COMMON_GUIDE_MESSAGES.forEach(m => cacheGuideAudio(m).catch(() => {}));
  }

  async function startCamera() {
    if (isLoadingRef.current || isCameraOn) return;
    if (!navigator.mediaDevices?.getUserMedia) {
      const msg = 'Cần HTTPS để mở camera.';
      setCameraError(msg);
      speak(msg, true);
      fileInputRef.current?.click();
      return;
    }
    try {
      setCameraError('');
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: 1280, height: 720 },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setIsCameraOn(true);
      const msg = 'Camera đã bật.';
      setStatus(msg);
      speak(msg, true);
      preloadGuideAudios();
    } catch (error) {
      const msg = 'Lỗi camera.';
      setCameraError(msg);
      speak(msg, true);
    }
  }

  function stopCamera() {
    stopGuidanceLoop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setIsCameraOn(false);
    readyCountRef.current = 0;
    autoCaptureRef.current = false;
  }

  async function captureCameraImage() {
    if (isLoadingRef.current) return;
    const blob = await getCameraFrameBlob({ quality: 0.95 });
    if (!blob) {
      speak('Không chụp được ảnh.', true);
      return;
    }
    stopGuidanceLoop();
    const file = new File([blob], `cam-${Date.now()}.jpg`, { type: 'image/jpeg' });
    await sendImageToBackend(file);
  }

  async function handleFileChange(event) {
    const file = event.target.files[0];
    if (!file) return;
    await sendImageToBackend(file);
    event.target.value = null;
  }

  async function sendImageToBackend(file) {
    const msg = 'Đang gửi tài liệu cho AI đọc, vui lòng chờ.';
    setStatus(msg);
    speak(msg, true);
    setIsLoading(true);
    try {
      const endpoint = isRemoteScannerMode ? '/upload?play_on_server=true' : '/upload';
      const { response, backendBaseUrl } = await postFileWithFallback(endpoint, file, 120000);
      if (response.data.audio_url) {
        stopCamera();
        if (isRemoteScannerMode) {
          speak('Đã gửi tài liệu.', true);
          return;
        }
        setStatus(`Xong. Nội dung: ${response.data.text}`);
        audioRef.current.src = backendBaseUrl + response.data.audio_url;
        await audioRef.current.play();
      } else {
        speak('Không tìm thấy văn bản.', true);
      }
    } catch (error) {
      speak('Lỗi kết nối máy chủ.', true);
    } finally {
      setIsLoading(false);
    }
  }

  function startGuidanceLoop() {
    if (guideTimerRef.current) return;
    requestGuidance();
    guideTimerRef.current = window.setInterval(requestGuidance, GUIDE_INTERVAL_MS);
  }

  function stopGuidanceLoop() {
    if (guideTimerRef.current) {
      window.clearInterval(guideTimerRef.current);
      guideTimerRef.current = null;
    }
    guideInFlightRef.current = false;
  }

  async function requestGuidance() {
    if (guideInFlightRef.current || isLoadingRef.current || !streamRef.current || autoCaptureRef.current) return;
    guideInFlightRef.current = true;
    try {
      const blob = await getCameraFrameBlob({ quality: 0.7, maxWidth: 640 });
      if (!blob) return;
      const file = new File([blob], `g-${Date.now()}.jpg`, { type: 'image/jpeg' });
      const { response } = await postFileWithFallback('/guide', file, 5000);
      const data = response.data;
      const msg = data?.message || 'Đang kiểm tra.';
      setGuideMessage(msg);
      setStatus(msg);
      if (data?.capture_ready) {
        readyCountRef.current += 1;
        if (readyCountRef.current >= READY_CHECKS_BEFORE_CAPTURE && !autoCaptureRef.current) {
          autoCaptureRef.current = true;
          const capMsg = 'Tài liệu đã rõ. Giữ yên, hệ thống sẽ chụp.';
          speak(capMsg, true);
          window.setTimeout(captureCameraImage, 800);
        }
      } else {
        speak(msg);
        readyCountRef.current = 0;
      }
    } catch (e) {
      console.error(e);
    } finally {
      guideInFlightRef.current = false;
    }
  }

  async function getCameraFrameBlob({ quality, maxWidth }) {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !video.videoWidth) return null;
    const scale = maxWidth && video.videoWidth > maxWidth ? maxWidth / video.videoWidth : 1;
    canvas.width = video.videoWidth * scale;
    canvas.height = video.videoHeight * scale;
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
    return new Promise(r => canvas.toBlob(r, 'image/jpeg', quality));
  }

  async function postFileWithFallback(endpoint, file, timeout) {
    let lastError;
    for (const url of uniqueUrls(backendCandidates)) {
      try {
        const fd = new FormData();
        fd.append('file', file);
        const res = await axios.post(`${url}${endpoint}`, fd, { timeout });
        activeBackendBaseUrlRef.current = url;
        return { response: res, backendBaseUrl: url };
      } catch (e) { lastError = e; }
    }
    throw lastError;
  }

  async function postJsonWithFallback(endpoint, payload, timeout) {
    let lastError;
    for (const url of uniqueUrls(backendCandidates)) {
      try {
        const res = await axios.post(`${url}${endpoint}`, payload, { timeout });
        activeBackendBaseUrlRef.current = url;
        return { response: res, backendBaseUrl: url };
      } catch (e) { lastError = e; }
    }
    throw lastError;
  }

  async function getWithFallback(endpoint, timeout) {
    let lastError;
    for (const url of uniqueUrls(backendCandidates)) {
      try {
        const res = await axios.get(`${url}${endpoint}`, { timeout });
        activeBackendBaseUrlRef.current = url;
        return { response: res, backendBaseUrl: url };
      } catch (e) { lastError = e; }
    }
    throw lastError;
  }

  async function pollLatestReading() {
    try {
      const { response, backendBaseUrl } = await getWithFallback('/latest-reading', 5000);
      const reading = response.data || {};
      if (!reading.id) {
        setReaderStatus('Đang chờ tài liệu từ điện thoại...');
        return;
      }
      const createdAt = Number(reading.created_at || 0);
      if (createdAt < readerStartedAtRef.current) {
        readerLastIdRef.current = reading.id;
        setReaderText(reading.text || '');
        setReaderStatus('Sẵn sàng nhận tài liệu mới.');
        return;
      }
      if (readerLastIdRef.current === reading.id) return;
      readerLastIdRef.current = reading.id;
      setReaderText(reading.text || '');
      setReaderStatus('Đã nhận tài liệu từ điện thoại. Đang đọc...');
      if (!audioRef.current || !reading.audio_url) return;
      audioRef.current.src = backendBaseUrl + reading.audio_url;
      await audioRef.current.play();
      audioRef.current.onended = () => {
        setReaderStatus('Đã đọc xong. Chờ tài liệu tiếp theo...');
      };
    } catch (e) {
      setReaderStatus('Lỗi kết nối.');
    }
  }

  function handleScannerScreenTap() {
    if (guideAudioRef.current) {
      guideAudioRef.current.play().catch(() => {});
      guideAudioRef.current.pause();
    }
    if (isLoadingRef.current) return;
    isCameraOn ? captureCameraImage() : startCamera();
  }

  function startComputerReader() {
    readerStartedAtRef.current = Date.now() / 1000 - 1;
    readerLastIdRef.current = '';
    setIsReaderListening(true);
  }

  function stopComputerReader() {
    setIsReaderListening(false);
    if (audioRef.current) audioRef.current.pause();
  }

  // Giao diện cho điện thoại (Scanner)
  if (showScanner || isRemoteScannerMode) {
    return (
      <main className="scanner-shell" onClick={handleScannerScreenTap}>
        <section className="scanner-panel">
          <div className="scanner-camera-stage">
            <video ref={videoRef} className="camera-view" playsInline muted />
            {!isCameraOn && <div className="camera-placeholder"><span>{isLoading ? 'Đang xử lý' : 'Chạm để quét'}</span></div>}
          </div>
          <div className="guide-box scanner-guide"><strong>Hướng dẫn</strong><span>{guideMessage}</span></div>
          {cameraError && <p className="error-text scanner-error">{cameraError}</p>}
          <div className="status-box scanner-status"><p>{status}</p></div>
          <div className="actions scanner-actions">
            <button type="button" onClick={(e) => { e.stopPropagation(); setShowScanner(false); }}>Thường</button>
            <button type="button" onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}>Chọn ảnh</button>
          </div>
          <audio ref={audioRef} style={{ display: 'none' }} />
          <audio ref={guideAudioRef} style={{ display: 'none' }} />
          <input ref={fileInputRef} type="file" accept="image/*" capture="environment" onChange={handleFileChange} style={{ display: 'none' }} />
          <canvas ref={canvasRef} style={{ display: 'none' }} />
        </section>
      </main>
    );
  }

  // Giao diện cho máy tính (Hybrid: Quét + Nhận từ điện thoại)
  return (
    <main className="app-shell">
      <section className="reader-panel">
        <div className="reader-header">
          <h1>Hỗ trợ đọc tài liệu</h1>
          <p className={isLoading ? 'state busy' : isCameraOn ? 'state guiding' : 'state ready'}>{isLoading ? 'AI...' : 'Sẵn sàng'}</p>
        </div>

        <div className="camera-stage">
          <video ref={videoRef} className="camera-view" playsInline muted />
          {!isCameraOn && <div className="camera-placeholder"><span>Camera máy tính chưa bật</span></div>}
        </div>

        <div className="guide-box">
          <strong>Hướng dẫn:</strong>
          <span>{guideMessage}</span>
        </div>

        <div className="actions">
          <button type="button" onClick={startCamera} disabled={isLoading || isCameraOn}>Bật camera</button>
          <button type="button" onClick={captureCameraImage} disabled={isLoading || !isCameraOn}>Chụp ảnh</button>
          <button type="button" onClick={stopCamera} disabled={isLoading || !isCameraOn}>Tắt camera</button>
          <button type="button" onClick={() => fileInputRef.current?.click()} disabled={isLoading}>Chọn ảnh</button>
        </div>

        <div className="status-box"><p>{status}</p></div>

        {/* MỤC MỚI: NHẬN DỮ LIỆU TỪ ĐIỆN THOẠI */}
        <div className="computer-receiver-section">
          <div className="receiver-header">
            <h3>Dữ liệu từ điện thoại</h3>
            <div className={`status-tag ${isReaderListening ? 'active' : ''}`}>
              {isReaderListening ? 'Đang kết nối 📡' : 'Đã tắt'}
            </div>
          </div>
          
          <div className="receiver-content">
            <div className="receiver-status-text">{readerStatus}</div>
            <div className={`received-text-box ${readerText ? 'has-text' : ''}`}>
              {readerText || 'Chưa có dữ liệu từ điện thoại...'}
            </div>
            <div className="receiver-controls">
              <button className="btn-small" onClick={isReaderListening ? stopComputerReader : startComputerReader}>
                {isReaderListening ? 'Tắt nhận' : 'Bật nhận'}
              </button>
              <button className="btn-small outline" onClick={() => speak('Âm thanh ổn định.')}>Thử loa</button>
            </div>
          </div>
        </div>

        <audio ref={audioRef} controls className="audio-player" />
        <audio ref={guideAudioRef} style={{ display: 'none' }} />
        <input ref={fileInputRef} type="file" accept="image/*" onChange={handleFileChange} style={{ display: 'none' }} />
        <canvas ref={canvasRef} style={{ display: 'none' }} />
      </section>
    </main>
  );
}

export default App;

function getAppMode() {
  const params = new URLSearchParams(window.location.search);
  const mode = (params.get('mode') || params.get('role') || '').toLowerCase();
  if (['scanner', 'phone', 'mobile'].includes(mode)) return 'scanner';
  if (['reader', 'computer', 'server'].includes(mode)) return 'reader';
  return window.innerWidth <= 768 ? 'scanner' : 'default';
}

function uniqueUrls(urls) {
  return [...new Set(urls.map((url) => url.replace(/\/$/, '')))];
}
