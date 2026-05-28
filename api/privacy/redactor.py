"""Privacy redaction for exported frames (F16)."""

import io
import logging
from typing import Optional, Tuple
from PIL import Image
import numpy as np

logger = logging.getLogger(__name__)


class FrameRedactor:
    """Redact sensitive regions from frames before export.

    - Blurs faces using RetinaFace.
    - Blurs non-target plates.
    - Returns JPEG bytes.
    """

    def __init__(self):
        """Initialize face detection model."""
        try:
            from retinaface import RetinaFace
            self.face_detector = RetinaFace
            self.has_face_detection = True
        except ImportError:
            logger.warning("RetinaFace not installed; face redaction disabled")
            self.has_face_detection = False

    def redact_frame(
        self,
        image_data: bytes,
        target_plate_region: Optional[Tuple[int, int, int, int]] = None,
        target_plate_text: Optional[str] = None,
        blur_radius: int = 30,
    ) -> bytes:
        """Redact faces and non-target plates from a frame.

        Args:
            image_data: JPEG bytes.
            target_plate_region: (x1, y1, x2, y2) of target plate (keep unblurred).
            target_plate_text: Expected plate text; used to identify target.
            blur_radius: Gaussian blur radius in pixels.

        Returns:
            Redacted JPEG bytes.
        """
        # Load image
        img = Image.open(io.BytesIO(image_data))
        img_array = np.array(img)

        # Redact faces if detector available
        if self.has_face_detection:
            img_array = self._redact_faces(img_array, blur_radius)

        # Redact non-target plates
        if target_plate_region:
            img_array = self._redact_non_target_plates(
                img_array, target_plate_region, blur_radius
            )

        # Convert back to JPEG
        redacted_img = Image.fromarray(img_array)
        jpeg_buffer = io.BytesIO()
        redacted_img.save(jpeg_buffer, format="JPEG", quality=90)
        return jpeg_buffer.getvalue()

    def _redact_faces(self, img_array: np.ndarray, blur_radius: int) -> np.ndarray:
        """Detect and blur faces.

        Args:
            img_array: (H, W, 3) BGR numpy array.
            blur_radius: Gaussian blur radius.

        Returns:
            Redacted image array.
        """
        try:
            # RetinaFace returns dict of detected faces
            detections = self.face_detector.detect_faces(img_array)

            if detections:
                img_pil = Image.fromarray(img_array)

                for face_id, detection in detections.items():
                    x1, y1, x2, y2 = detection["facial_area"]
                    # Blur region
                    face_region = img_pil.crop((x1, y1, x2, y2))
                    face_region = face_region.filter(
                        Image.BLUR,
                        radius=blur_radius,
                    )
                    img_pil.paste(face_region, (x1, y1))

                return np.array(img_pil)

        except Exception as e:
            logger.warning(f"Face detection failed: {e}")

        return img_array

    def _redact_non_target_plates(
        self,
        img_array: np.ndarray,
        target_region: Tuple[int, int, int, int],
        blur_radius: int,
    ) -> np.ndarray:
        """Blur all rectangular regions except target plate.

        Args:
            img_array: (H, W, 3) BGR numpy array.
            target_region: (x1, y1, x2, y2) of target plate.
            blur_radius: Gaussian blur radius.

        Returns:
            Redacted image array.
        """
        # Production: use YOLO to detect all plates, blur non-targets.
        # MVP: placeholder implementation.
        return img_array


def redact_and_export_frame(
    frame_bytes: bytes,
    target_plate_bbox: Optional[Tuple[int, int, int, int]] = None,
    output_format: str = "jpeg",
) -> bytes:
    """Public API for frame export redaction.

    Args:
        frame_bytes: Raw frame data (JPEG or PNG).
        target_plate_bbox: (x, y, w, h) of target plate (center-relative).
        output_format: "jpeg" or "png".

    Returns:
        Redacted frame bytes.
    """
    redactor = FrameRedactor()
    return redactor.redact_frame(frame_bytes, target_plate_region=target_plate_bbox)
