"""ANPR live demo: source → detect → overlay.

Run: uv run python -m scripts.demo --source webcam
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import Optional

import cv2

from anpr_core.detect.yolo_detector import YOLODetector
from anpr_core.pipeline.scheduler import FrameScheduler
from ingest.file import FileSource
from ingest.iphone import iPhoneSource
from ingest.rtsp import RTSPSource
from ingest.webcam import WebcamSource

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)


def create_source(args: argparse.Namespace):
    if args.source == "webcam":
        return WebcamSource(index=args.index)
    elif args.source == "iphone":
        return iPhoneSource(source="continuity", device_index=args.index)
    elif args.source == "rtsp":
        if not args.url:
            raise ValueError("--url required for --source rtsp")
        return RTSPSource(url=args.url)
    elif args.source == "file":
        if not args.url:
            raise ValueError("--url required for --source file")
        return FileSource(path=args.url)
    else:
        raise ValueError(f"Unknown source: {args.source}")


def draw_detection(image, det, color=(0, 255, 0), thickness=2):
    x1, y1, x2, y2 = int(det.x1), int(det.y1), int(det.x2), int(det.y2)
    cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
    text = f"{det.class_name} {det.conf:.2f}"
    cv2.putText(image, text, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)


def main() -> int:
    parser = argparse.ArgumentParser(description="ANPR live demo")
    parser.add_argument(
        "--source",
        choices=["webcam", "iphone", "rtsp", "file"],
        default="webcam",
        help="Frame source",
    )
    parser.add_argument("--url", help="RTSP URL or file path")
    parser.add_argument("--index", type=int, default=0, help="cv2 device index")
    parser.add_argument("--model", default="yolov8s.pt", help="YOLO model")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--device", default="auto", help="Device (auto|cpu|cuda:0|mps)")
    args = parser.parse_args()

    logger.info(f"Starting ANPR demo: {args.source}")

    try:
        source = create_source(args)
        detector = YOLODetector(model=args.model, device=args.device, conf=args.conf)

        with FrameScheduler(source, max_queue=5) as scheduler:
            window = "ANPR — press q to quit"
            cv2.namedWindow(window, cv2.WINDOW_NORMAL)

            stats_frame_count = 0
            ts_start = time.time()

            while True:
                frame_obj = scheduler.get(timeout=0.1)
                if frame_obj is None:
                    if scheduler._stop:
                        break
                    continue

                image = frame_obj.image.copy()
                detections = detector.detect(image)

                for det in detections:
                    draw_detection(image, det)

                stats_frame_count += 1
                elapsed = time.time() - ts_start
                fps = stats_frame_count / elapsed if elapsed > 0 else 0

                info = f"frames={stats_frame_count} fps={fps:.1f} drops={scheduler.stats.frames_dropped}"
                cv2.putText(
                    image, info, (10, image.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1
                )

                cv2.imshow(window, image)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        cv2.destroyAllWindows()
        logger.info(f"Demo complete: {stats_frame_count} frames in {elapsed:.1f}s ({fps:.1f} fps)")
        return 0

    except Exception as e:
        logger.exception(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
