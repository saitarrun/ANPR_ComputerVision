"""Smoke test: verify cv2.VideoCapture can open the laptop camera.

Run: uv run python scripts/smoke_webcam.py [--index 0]
Press q to quit.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import deque
from datetime import datetime

import cv2


def main() -> int:
    parser = argparse.ArgumentParser(description="Webcam smoke test")
    parser.add_argument("--index", type=int, default=0, help="cv2.VideoCapture index")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.index)
    if not cap.isOpened():
        print(f"ERROR: cannot open camera index {args.index}", file=sys.stderr)
        print("On macOS, grant Terminal/IDE camera permission in System Settings → Privacy.", file=sys.stderr)
        return 1

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    window = "ANPR smoke — press q to quit"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)

    frame_times: deque[float] = deque(maxlen=30)
    print(f"Opened camera {args.index}. Press q in the window to quit.")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("ERROR: failed to read frame", file=sys.stderr)
                return 2

            now = time.perf_counter()
            frame_times.append(now)
            fps = 0.0
            if len(frame_times) >= 2:
                fps = (len(frame_times) - 1) / (frame_times[-1] - frame_times[0])

            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            cv2.putText(frame, ts, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"{fps:5.1f} fps", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            cv2.imshow(window, frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    sys.exit(main())
