"""Finds your face and picks a 9:16 crop for each kept segment.

One crop per segment (not a drifting pan), so the frame only moves on a jump
cut, which reads as intentional. Every other jump cut gets a slight punch-in.
"""
from __future__ import annotations

import statistics

from .media import Probe

SAMPLES_PER_SEC = 3


def detect_faces(probe: Probe) -> list[tuple[float, float, float, float]]:
    """Returns (time, center_x, center_y, face_height), all as fractions of the frame."""
    import cv2

    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(str(probe.path))
    step = max(1, round(probe.fps / SAMPLES_PER_SEC))
    found, i = [], 0
    while True:
        if not cap.grab():
            break
        if i % step == 0:
            ok, frame = cap.retrieve()
            if ok:
                t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
                fh, fw = frame.shape[:2]
                # If OpenCV didn't apply the phone's rotation, do it here.
                if (fw > fh) != (probe.width > probe.height) and probe.rotation:
                    rot = probe.rotation % 360
                    frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE if rot == 90
                                       else cv2.ROTATE_90_CLOCKWISE if rot == 270 else cv2.ROTATE_180)
                    fh, fw = frame.shape[:2]
                scale = 720 / max(fw, fh)
                small = cv2.resize(frame, (int(fw * scale), int(fh * scale)))
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(32, 32))
                if len(faces):
                    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                    sh, sw = gray.shape
                    found.append((t, (x + w / 2) / sw, (y + h / 2) / sh, h / sh))
        i += 1
    cap.release()
    return found


def plan_crops(segments: list[dict], faces: list[tuple], probe: Probe,
               out_w: int, out_h: int, punch_in: float, face_height: float) -> None:
    """Adds crop boxes (x, y, w, h in source pixels) and zoom to each segment, in place."""
    W, H = probe.width, probe.height
    target = out_w / out_h
    base_w, base_h = (H * target, H) if W / H > target else (W, W / target)

    all_x = [f[1] for f in faces] or [0.5]
    all_y = [f[2] for f in faces] or [0.42]
    gx, gy = statistics.median(all_x), statistics.median(all_y)

    for i, seg in enumerate(segments):
        inside = [f for f in faces if seg["start"] - 0.2 <= f[0] <= seg["end"] + 0.2]
        if not inside and faces:
            nearest = min(faces, key=lambda f: abs(f[0] - (seg["start"] + seg["end"]) / 2))
            inside = [nearest] if abs(nearest[0] - seg["start"]) < 3 else []
        cx = statistics.median(f[1] for f in inside) if inside else gx
        cy = statistics.median(f[2] for f in inside) if inside else gy

        zoom = punch_in if (i % 2 == 1 and seg["end"] - seg["start"] >= 1.0) else 1.0
        cw, ch = base_w / zoom, base_h / zoom
        x = min(max(cx * W - cw / 2, 0), W - cw)
        y = min(max(cy * H - face_height * ch, 0), H - ch) if ch < H - 1 else 0
        seg.update(zoom=round(zoom, 3), crop=[_even(x), _even(y), _even(cw), _even(ch)],
                   face=[round(cx, 3), round(cy, 3)] if inside else None)


def _even(v: float) -> int:
    return int(v) // 2 * 2
