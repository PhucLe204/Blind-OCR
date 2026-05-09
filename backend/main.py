from __future__ import annotations

import shutil
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from gtts import gTTS

try:
    from .ocr_engine import process_image
except ImportError:
    from ocr_engine import process_image


BASE_DIR = Path(__file__).resolve().parent
TEMP_IMAGE_DIR = BASE_DIR / "temp_images"
STATIC_AUDIO_DIR = BASE_DIR / "static_audio"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_IMAGE_DIR.mkdir(exist_ok=True)
STATIC_AUDIO_DIR.mkdir(exist_ok=True)
app.mount("/audio", StaticFiles(directory=str(STATIC_AUDIO_DIR)), name="audio")


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    image_path = TEMP_IMAGE_DIR / f"{file_id}.jpg"
    audio_path = STATIC_AUDIO_DIR / f"{file_id}.mp3"

    with image_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    _cleanup_old_audio_files()

    try:
        text = process_image(str(image_path))
        gTTS(text=text, lang="vi").save(str(audio_path))

        return {
            "text": text,
            "audio_url": f"/audio/{file_id}.mp3",
        }
    except Exception as exc:
        import traceback

        traceback.print_exc()
        if audio_path.exists():
            audio_path.unlink()
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý ảnh: {exc}") from exc
    finally:
        if image_path.exists():
            image_path.unlink()


def _cleanup_old_audio_files(max_age_seconds: int = 300) -> None:
    now = time.time()
    for path in STATIC_AUDIO_DIR.iterdir():
        if path.is_file() and now - path.stat().st_mtime > max_age_seconds:
            try:
                path.unlink()
            except OSError:
                pass
