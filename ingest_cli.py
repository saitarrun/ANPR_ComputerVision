"""CLI for ingesting frames via FastAPI backend."""

import argparse
import base64
import logging
import sys
from typing import Optional

import cv2
import requests

from ingest.base import FrameSource
from ingest.webcam import WebcamSource
from ingest.rtsp import RTSPSource
from ingest.file import FileSource
from ingest.iphone import iPhoneSource

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class APIIngestClient:
    """Client for sending frames to ANPR backend API."""

    def __init__(self, api_url: str = "http://localhost:8000", token: Optional[str] = None):
        self.api_url = api_url
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def ingest_frame(self, stream_id: str, frame_bytes: bytes, camera_id: str) -> Optional[str]:
        """Send frame to API.

        Args:
            stream_id: Stream identifier
            frame_bytes: Raw JPEG bytes
            camera_id: Camera identifier

        Returns:
            Task ID or None on error
        """
        try:
            frame_b64 = base64.b64encode(frame_bytes).decode()
            response = self.session.post(
                f"{self.api_url}/v1/ingest/frame",
                json={
                    "stream_id": stream_id,
                    "frame_b64_jpeg": frame_b64,
                    "camera_id": camera_id,
                },
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("task_id")
            else:
                logger.error(f"API error: {response.status_code} {response.text}")
                return None
        except Exception as e:
            logger.error(f"Failed to ingest frame: {e}")
            return None

    def get_task_status(self, task_id: str) -> Optional[dict]:
        """Poll task status.

        Args:
            task_id: Celery task ID

        Returns:
            Task status dict or None
        """
        try:
            response = self.session.get(f"{self.api_url}/v1/ingest/task/{task_id}")
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get task status: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Failed to fetch task status: {e}")
            return None


def ingest_from_source(
    source: FrameSource,
    stream_id: str,
    camera_id: str,
    api_client: APIIngestClient,
    max_frames: Optional[int] = None,
) -> None:
    """Read frames from source and send to API.

    Args:
        source: Frame source (webcam, RTSP, file, etc.)
        stream_id: Stream identifier
        camera_id: Camera identifier
        api_client: API client
        max_frames: Max frames to ingest (None = unlimited)
    """
    frame_count = 0
    task_count = 0

    try:
        while True:
            if max_frames and frame_count >= max_frames:
                break

            frame = source.read()
            if frame is None:
                break

            # Encode to JPEG bytes
            _, jpeg_bytes = cv2.imencode(".jpg", frame.image)

            # Send to API
            task_id = api_client.ingest_frame(stream_id, jpeg_bytes.tobytes(), camera_id)
            if task_id:
                logger.info(f"Frame {frame_count}: queued task={task_id}")
                task_count += 1
            else:
                logger.warning(f"Frame {frame_count}: failed to queue")

            frame_count += 1

            if frame_count % 30 == 0:
                logger.info(f"Queued {task_count}/{frame_count} frames")

    finally:
        source.close()
        logger.info(f"Ingestion complete: {frame_count} frames, {task_count} tasks queued")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Ingest frames via ANPR API")
    parser.add_argument("--source", choices=["webcam", "rtsp", "file", "iphone"], default="webcam")
    parser.add_argument("--url", help="RTSP/file URL")
    parser.add_argument("--stream-id", default="default-stream")
    parser.add_argument("--camera-id", default="camera-1")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--token", help="JWT token for authentication")
    parser.add_argument("--max-frames", type=int, help="Max frames to ingest")

    args = parser.parse_args()

    # Initialize source
    source: Optional[FrameSource] = None
    if args.source == "webcam":
        source = WebcamSource()
    elif args.source == "rtsp":
        if not args.url:
            print("--url required for RTSP source")
            sys.exit(1)
        source = RTSPSource(args.url)
    elif args.source == "file":
        if not args.url:
            print("--url required for file source")
            sys.exit(1)
        source = FileSource(args.url)
    elif args.source == "iphone":
        source = iPhoneSource()

    if not source:
        print("Failed to initialize source")
        sys.exit(1)

    # Initialize API client
    api_client = APIIngestClient(api_url=args.api_url, token=args.token)

    # Ingest frames
    try:
        ingest_from_source(
            source,
            stream_id=args.stream_id,
            camera_id=args.camera_id,
            api_client=api_client,
            max_frames=args.max_frames,
        )
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
