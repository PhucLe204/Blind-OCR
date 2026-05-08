import os, uuid, shutil
# pyrefly: ignore [missing-import]
from fastapi import FastAPI, UploadFile, File, HTTPException
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from fastapi.staticfiles import StaticFiles
# pyrefly: ignore [missing-import]
from gtts import gTTS
from ocr_engine import process_image

app = FastAPI()

# Cấp quyền cho React (Port 5173) gọi vào Backend (Port 8000)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

os.makedirs("temp_images", exist_ok=True)
os.makedirs("static_audio", exist_ok=True)
app.mount("/audio", StaticFiles(directory="static_audio"), name="audio")

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    img_path = f"temp_images/{file_id}.jpg"
    
    with open(img_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Dọn dẹp rác: Xóa các file âm thanh cũ hơn 5 phút để chống đầy ổ cứng
    import time
    now = time.time()
    for f in os.listdir("static_audio"):
        fpath = os.path.join("static_audio", f)
        if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > 300:
            try:
                os.remove(fpath)
            except:
                pass
    
    try:
        # Chạy AI đọc chữ
        text = process_image(img_path)
        # Chuyển thành giọng nói MP3
        audio_path = f"static_audio/{file_id}.mp3"
        gTTS(text=text, lang='vi').save(audio_path)
        
        return {
            "text": text,
            "audio_url": f"/audio/{file_id}.mp3"
        }
    except Exception as e:
        # In chi tiết lỗi ra console để debug
        import traceback
        traceback.print_exc()
        
        # Xóa file audio nếu tạo lỗi giữa chừng
        audio_path = f"static_audio/{file_id}.mp3"
        if os.path.exists(audio_path):
            os.remove(audio_path)
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý ảnh: {str(e)}")
    finally:
        if os.path.exists(img_path): os.remove(img_path)