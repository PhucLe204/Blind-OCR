from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "segmentation" / "best.pt"

MODEL_PATH = Path(os.getenv("DOCUMENT_DETECTOR_MODEL", str(DEFAULT_MODEL_PATH)))
CONF_THRESHOLD = float(os.getenv("DOCUMENT_DETECTOR_CONF", "0.25"))
IMGSZ = int(os.getenv("DOCUMENT_DETECTOR_IMGSZ", "640"))
MIN_AREA_RATIO = float(os.getenv("DOCUMENT_DETECTOR_MIN_AREA_RATIO", "0.03"))
CROP_PADDING_RATIO = float(os.getenv("DOCUMENT_CROP_PADDING_RATIO", "0.04"))


@lru_cache(maxsize=1)
def _load_model() -> Any | None:
    if not MODEL_PATH.exists():
        print(f"Document detector disabled: model not found at {MODEL_PATH}")
        return None

    try:
        from ultralytics import YOLO

        return YOLO(str(MODEL_PATH))
    except Exception as exc:
        print(f"Document detector disabled: {exc}")
        return None


def extract_document_region(image: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    """Use the segmentation YOLO model to crop/deskew the document before OCR."""
    if image is None or image.size == 0:
        return image, {"status": "invalid_image"}

    model = _load_model()
    if model is None:
        return image, {"status": "detector_unavailable"}

    try:
        predictions = model.predict(
            source=image,
            conf=CONF_THRESHOLD,
            imgsz=IMGSZ,
            verbose=False,
        )
    except Exception as exc:
        print(f"Document detector error: {exc}")
        return image, {"status": "detector_error", "error": str(exc)}

    if not predictions:
        return image, {"status": "no_detection"}

    result = predictions[0]
    selected = _select_detection(result, image.shape[:2])
    if selected is None:
        return image, {"status": "no_detection"}

    index, bbox, confidence = selected

    contour = _contour_from_masks(result, index, image.shape[:2])
    if contour is not None:
        cropped, method = _crop_from_contour(image, contour)
    else:
        cropped, method = _crop_from_bbox(image, bbox)

    if cropped is None or cropped.size == 0:
        return image, {"status": "crop_failed"}

    return cropped, {
        "status": "detected",
        "method": method,
        "confidence": confidence,
        "bbox": [int(v) for v in bbox],
    }


def _select_detection(
    result: Any,
    image_shape: tuple[int, int],
) -> tuple[int, np.ndarray, float] | None:
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return None

    xyxy = _to_numpy(boxes.xyxy).astype(np.float32).reshape(-1, 4)
    if xyxy.size == 0:
        return None

    if getattr(boxes, "conf", None) is not None:
        confidences = _to_numpy(boxes.conf).astype(np.float32).reshape(-1)
    else:
        confidences = np.ones((len(xyxy),), dtype=np.float32)

    image_h, image_w = image_shape
    image_area = float(max(1, image_h * image_w))
    scores: list[float] = []

    for bbox, confidence in zip(xyxy, confidences):
        x1, y1, x2, y2 = _clip_bbox(bbox, image_w, image_h)
        area = max(0, x2 - x1) * max(0, y2 - y1)
        if area / image_area < MIN_AREA_RATIO or confidence < CONF_THRESHOLD:
            scores.append(-1.0)
        else:
            scores.append(float(area) * max(float(confidence), 0.01))

    best_index = int(np.argmax(scores))
    if scores[best_index] < 0:
        return None

    bbox = _clip_bbox(xyxy[best_index], image_w, image_h)
    return best_index, np.array(bbox, dtype=np.float32), float(confidences[best_index])


def _contour_from_masks(
    result: Any,
    index: int,
    image_shape: tuple[int, int],
) -> np.ndarray | None:
    masks = getattr(result, "masks", None)
    if masks is None:
        return None

    polygons = getattr(masks, "xy", None)
    if polygons is not None and len(polygons) > index and len(polygons[index]) >= 4:
        return np.asarray(polygons[index], dtype=np.float32).reshape(-1, 1, 2)

    data = getattr(masks, "data", None)
    if data is None or len(data) <= index:
        return None

    image_h, image_w = image_shape
    mask = _to_numpy(data[index])
    mask = cv2.resize(mask, (image_w, image_h), interpolation=cv2.INTER_NEAREST)
    mask = (mask > 0.5).astype(np.uint8) * 255

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    return max(contours, key=cv2.contourArea)


def _crop_from_contour(image: np.ndarray, contour: np.ndarray) -> tuple[np.ndarray | None, str]:
    perimeter = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)

    if len(approx) == 4:
        warped = _four_point_warp(image, approx.reshape(4, 2).astype(np.float32))
        if warped is not None and warped.size > 0:
            return warped, "perspective"

    x, y, w, h = cv2.boundingRect(contour.astype(np.int32))
    return _crop_rect(image, x, y, x + w, y + h), "mask_bbox"


def _crop_from_bbox(image: np.ndarray, bbox: np.ndarray) -> tuple[np.ndarray | None, str]:
    x1, y1, x2, y2 = [int(v) for v in bbox]
    return _crop_rect(image, x1, y1, x2, y2), "bbox"


def _crop_rect(
    image: np.ndarray,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
) -> np.ndarray | None:
    image_h, image_w = image.shape[:2]
    width = max(1, x2 - x1)
    height = max(1, y2 - y1)
    pad_x = int(width * CROP_PADDING_RATIO)
    pad_y = int(height * CROP_PADDING_RATIO)

    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(image_w, x2 + pad_x)
    y2 = min(image_h, y2 + pad_y)

    if x2 <= x1 or y2 <= y1:
        return None

    return image[y1:y2, x1:x2].copy()


def _four_point_warp(image: np.ndarray, points: np.ndarray) -> np.ndarray | None:
    rect = _order_points(points)
    tl, tr, br, bl = rect

    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_width = int(max(width_a, width_b))

    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_height = int(max(height_a, height_b))

    if max_width < 8 or max_height < 8:
        return None

    destination = np.array(
        [
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1],
        ],
        dtype=np.float32,
    )

    matrix = cv2.getPerspectiveTransform(rect, destination)
    return cv2.warpPerspective(image, matrix, (max_width, max_height))


def _order_points(points: np.ndarray) -> np.ndarray:
    rect = np.zeros((4, 2), dtype=np.float32)
    point_sum = points.sum(axis=1)
    point_diff = np.diff(points, axis=1)

    rect[0] = points[np.argmin(point_sum)]
    rect[2] = points[np.argmax(point_sum)]
    rect[1] = points[np.argmin(point_diff)]
    rect[3] = points[np.argmax(point_diff)]
    return rect


def _clip_bbox(bbox: np.ndarray, image_w: int, image_h: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = [int(round(v)) for v in bbox[:4]]
    x1 = max(0, min(image_w - 1, x1))
    y1 = max(0, min(image_h - 1, y1))
    x2 = max(0, min(image_w, x2))
    y2 = max(0, min(image_h, y2))
    return x1, y1, x2, y2


def _to_numpy(value: Any) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    return np.asarray(value)
