"""End-to-end demo: ingest frames via API, receive detections via WebSocket."""

import argparse
import asyncio
import base64
import json
import logging
import sys
from typing import Optional

import cv2
import requests
import websockets

from ingest.base import FrameSource
from ingest.webcam import WebcamSource
from ingest.file import FileSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class ANPRDemo:
    """Full ANPR pipeline demo."""

    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        email: str = "demo@example.com",
        password: str = "demo123",
    ):
        self.api_url = api_url
        self.email = email
        self.password = password
        self.token: Optional[str] = None
        self.session = requests.Session()

    async def login(self) -> bool:
        """Authenticate and get JWT token."""
        try:
            response = self.session.post(
                f"{self.api_url}/v1/auth/login",
                json={"email": self.email, "password": self.password},
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                self.session.headers.update({"Authorization": f"Bearer {self.token}"})
                logger.info(f"Authenticated as {self.email}")
                return True
            else:
                logger.error(f"Auth failed: {response.status_code} {response.text}")
                return False
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False

    def ingest_frame(self, stream_id: str, frame_bytes: bytes, camera_id: str) -> Optional[str]:
        """Send frame to ingest endpoint."""
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
                task_id = response.json().get("task_id")
                return task_id
            else:
                logger.warning(f"Ingest failed: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Ingest error: {e}")
            return None

    async def listen_detections(
        self,
        stream_id: str,
        callback=None,
    ) -> None:
        """Listen to WebSocket for detections."""
        ws_url = f"ws://localhost:8000/v1/stream/{stream_id}?token={self.token}"
        try:
            async with websockets.connect(ws_url) as ws:
                logger.info(f"Connected to WebSocket: {stream_id}")
                async for message in ws:
                    try:
                        data = json.loads(message)
                        logger.info(f"Detection: {data}")
                        if callback:
                            callback(data)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON: {message}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")

    async def run_demo(
        self,
        source: FrameSource,
        stream_id: str = "demo-stream",
        camera_id: str = "demo-camera",
        max_frames: Optional[int] = None,
    ) -> None:
        """Run full demo: ingest + listen."""
        # Auth
        if not await self.login():
            logger.error("Failed to authenticate")
            return

        frame_count = 0
        ingest_count = 0

        # Start WebSocket listener in background
        ws_task = asyncio.create_task(self.listen_detections(stream_id))

        # Ingest frames
        try:
            await asyncio.sleep(1)  # Let WebSocket connect

            while True:
                if max_frames and frame_count >= max_frames:
                    break

                frame = source.read()
                if frame is None:
                    break

                # Encode to JPEG
                _, jpeg_bytes = cv2.imencode(".jpg", frame.image)

                # Ingest
                task_id = self.ingest_frame(stream_id, jpeg_bytes.tobytes(), camera_id)
                if task_id:
                    logger.info(f"Frame {frame_count}: task={task_id}")
                    ingest_count += 1
                else:
                    logger.warning(f"Frame {frame_count}: ingest failed")

                frame_count += 1
                await asyncio.sleep(0.05)  # 20 fps
        finally:
            source.close()
            ws_task.cancel()
            logger.info(f"Demo complete: {frame_count} frames, {ingest_count} ingested")


async def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="ANPR end-to-end demo")
    parser.add_argument("--source", choices=["webcam", "file"], default="webcam")
    parser.add_argument("--file", help="Video file path (for file source)")
    parser.add_argument("--stream-id", default="demo-stream")
    parser.add_argument("--camera-id", default="demo-camera")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--email", default="demo@example.com")
    parser.add_argument("--password", default="demo123")
    parser.add_argument("--max-frames", type=int, help="Max frames")

    args = parser.parse_args()

    # Initialize source
    source: Optional[FrameSource] = None
    if args.source == "webcam":
        source = WebcamSource()
    elif args.source == "file":
        if not args.file:
            print("--file required for file source")
            sys.exit(1)
        source = FileSource(args.file)

    if not source:
        print("Failed to initialize source")
        sys.exit(1)

    # Run demo
    demo = ANPRDemo(
        api_url=args.api_url,
        email=args.email,
        password=args.password,
    )
    try:
        await demo.run_demo(
            source,
            stream_id=args.stream_id,
            camera_id=args.camera_id,
            max_frames=args.max_frames,
        )
    except KeyboardInterrupt:
        logger.info("Demo interrupted")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
