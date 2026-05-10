from __future__ import annotations

import base64
import os
import shutil
import subprocess
import time
import uuid
import hashlib
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from gtts import gTTS
from pydantic import BaseModel

try:
    from .document_detector import analyze_document_frame
    from .ocr_engine import process_image
except ImportError:
    from document_detector import analyze_document_frame
    from ocr_engine import process_image


BASE_DIR = Path(__file__).resolve().parent
TEMP_IMAGE_DIR = BASE_DIR / "temp_images"
STATIC_AUDIO_DIR = BASE_DIR / "static_audio"
LATEST_READING: dict[str, Any] | None = None


class GuideAudioRequest(BaseModel):
    text: str

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


@app.post("/guide")
async def guide_frame(file: UploadFile = File(...)):
    try:
        image_bytes = await file.read()
        image_array = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Invalid image")

        return analyze_document_frame(image)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Lỗi phân tích camera: {exc}") from exc


@app.post("/guide-audio")
async def guide_audio(request: GuideAudioRequest):
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Thiếu nội dung hướng dẫn.")

    text = text[:250]
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    filename = f"guide_{digest}.mp3"
    audio_path = STATIC_AUDIO_DIR / filename

    try:
        if not audio_path.exists():
            gTTS(text=text, lang="vi").save(str(audio_path))

        return {"audio_url": f"/audio/{filename}"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi tạo âm thanh hướng dẫn: {exc}") from exc


@app.post("/upload")
async def upload_file(file: UploadFile = File(...), play_on_server: bool = False):
    global LATEST_READING

    file_id = str(uuid.uuid4())
    image_path = TEMP_IMAGE_DIR / f"{file_id}.jpg"
    audio_path = STATIC_AUDIO_DIR / f"{file_id}.mp3"

    with image_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    _cleanup_old_audio_files()

    try:
        text = process_image(str(image_path))
        gTTS(text=text, lang="vi").save(str(audio_path))
        LATEST_READING = {
            "id": file_id,
            "text": text,
            "audio_url": f"/audio/{file_id}.mp3",
            "created_at": time.time(),
            "server_playback": False,
        }
        if play_on_server:
            LATEST_READING["server_playback"] = _play_audio_on_server(audio_path)

        return LATEST_READING
    except Exception as exc:
        import traceback

        traceback.print_exc()
        if audio_path.exists():
            audio_path.unlink()
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý ảnh: {exc}") from exc
    finally:
        if image_path.exists():
            image_path.unlink()


@app.get("/latest-reading")
async def latest_reading():
    if not LATEST_READING:
        return {
            "id": "",
            "text": "",
            "audio_url": "",
            "created_at": 0,
        }

    return LATEST_READING


def _cleanup_old_audio_files(max_age_seconds: int = 3600) -> None:
    now = time.time()
    for path in STATIC_AUDIO_DIR.iterdir():
        if path.is_file() and now - path.stat().st_mtime > max_age_seconds:
            try:
                path.unlink()
            except OSError:
                pass


def _play_audio_on_server(audio_path: Path) -> bool:
    if os.name != "nt" or not audio_path.exists():
        return False

    script = f"""
$player = New-Object -ComObject WMPlayer.OCX
$player.URL = '{str(audio_path).replace("'", "''")}'
$player.controls.play()
while ($player.playState -ne 1 -and $player.playState -ne 8) {{
    Start-Sleep -Milliseconds 250
}}
"""
    encoded_script = base64.b64encode(script.encode("utf-16le")).decode("ascii")

    try:
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-WindowStyle",
                "Hidden",
                "-EncodedCommand",
                encoded_script,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except OSError:
        return False
