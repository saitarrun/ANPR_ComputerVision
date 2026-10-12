"""Unit tests for anpr_core pure modules + crypto/security helpers.

Targets high-statement, low-coverage modules to keep the coverage gate green.
All tests are pure unit tests: no DB, no network, no model weights.
"""

import numpy as np
import pytest
from cryptography.fernet import Fernet

from anpr_core.detect.normalize import (
    PLATE_HEIGHT,
    PLATE_WIDTH,
    detect_corners_from_bbox,
    estimate_tilt_from_crop,
    normalize_plate,
)
from anpr_core.ocr.fuser import FusedOCRResult, OCRFuser
from anpr_core.ocr.paddle_backend import OCRResult
from anpr_core.postproc.regions.eu import EUPostprocessor
from anpr_core.postproc.regions.india import IndiaPostprocessor
from anpr_core.postproc.regions.us import USPostprocessor


class TestNormalizePlate:
    def test_empty_crop_returns_unchanged(self):
        crop = np.zeros((0, 0, 3), dtype=np.uint8)
        assert normalize_plate(crop) is crop

    def test_no_corners_produces_canonical_size(self):
        crop = np.random.randint(0, 255, (40, 120, 3), dtype=np.uint8)
        out = normalize_plate(crop)
        assert out.shape == (PLATE_HEIGHT, PLATE_WIDTH, 3)

    def test_with_explicit_corners(self):
        crop = np.random.randint(0, 255, (50, 150, 3), dtype=np.uint8)
        corners = np.array([[5, 5], [145, 2], [148, 48], [3, 45]], dtype=np.float32)
        out = normalize_plate(crop, corners)
        assert out.shape == (PLATE_HEIGHT, PLATE_WIDTH, 3)

    def test_corners_as_list(self):
        crop = np.random.randint(0, 255, (50, 150, 3), dtype=np.uint8)
        corners = [[0, 0], [150, 0], [150, 50], [0, 50]]
        out = normalize_plate(crop, corners)
        assert out.shape == (PLATE_HEIGHT, PLATE_WIDTH, 3)

    def test_canonical_constants(self):
        assert (PLATE_WIDTH, PLATE_HEIGHT) == (200, 60)


class TestDetectCornersFromBbox:
    def test_no_tilt_returns_bbox_corners(self):
        corners = detect_corners_from_bbox((10, 20, 110, 60), (480, 640, 3))
        expected = np.array([[10, 20], [110, 20], [110, 60], [10, 60]], dtype=np.float32)
        np.testing.assert_allclose(corners, expected, rtol=1e-5)

    def test_tilt_rotates_around_center(self):
        no_tilt = detect_corners_from_bbox((10, 20, 110, 60), (480, 640, 3))
        tilted = detect_corners_from_bbox((10, 20, 110, 60), (480, 640, 3), tilt_degrees=10.0)
        assert tilted.shape == (4, 2)
        # Center must be preserved by rotation
        np.testing.assert_allclose(tilted.mean(axis=0), no_tilt.mean(axis=0), rtol=1e-4)
        # Corners must actually move
        assert not np.allclose(tilted, no_tilt)

    def test_zero_tilt_equals_no_tilt(self):
        a = detect_corners_from_bbox((0, 0, 50, 20), (100, 100, 3))
        b = detect_corners_from_bbox((0, 0, 50, 20), (100, 100, 3), tilt_degrees=0.0)
        np.testing.assert_allclose(a, b)


class TestEstimateTilt:
    def test_blank_image_returns_zero(self):
        crop = np.zeros((60, 200, 3), dtype=np.uint8)
        assert estimate_tilt_from_crop(crop) == 0.0

    def test_result_within_bounds(self):
        rng = np.random.RandomState(42)
        crop = rng.randint(0, 255, (60, 200, 3), dtype=np.uint8)
        tilt = estimate_tilt_from_crop(crop)
        assert -25.0 <= tilt <= 25.0


class TestIndiaPostprocessor:
    def test_valid_plate(self):
        r = IndiaPostprocessor().postprocess("MH12AB1234")
        assert r.is_valid and r.plate_text == "MH12AB1234" and r.fixes_applied == []

    def test_lowercase_uppercased(self):
        r = IndiaPostprocessor().postprocess("mh12ab1234")
        assert r.is_valid and r.plate_text == "MH12AB1234"

    def test_confusion_fix_single_char(self):
        # 0/O confusion: MH12AB1234 with O instead of 0 is invalid, fixable
        r = IndiaPostprocessor().postprocess("MH12AB123O")
        assert r.is_valid and r.plate_text == "MH12AB1230"
        assert r.fixes_applied

    def test_garbage_stays_invalid(self):
        r = IndiaPostprocessor().postprocess("!!!")
        assert not r.is_valid

    def test_empty_stays_invalid(self):
        r = IndiaPostprocessor().postprocess("")
        assert not r.is_valid


class TestUSPostprocessor:
    def test_valid_letters_digits(self):
        r = USPostprocessor().postprocess("ABC1234")
        assert r.is_valid

    def test_valid_reversed(self):
        r = USPostprocessor().postprocess("1234ABC")
        assert r.is_valid

    def test_confusion_fix(self):
        r = USPostprocessor().postprocess("ABC123O")
        assert r.is_valid and r.plate_text == "ABC1230"

    def test_garbage_stays_invalid(self):
        r = USPostprocessor().postprocess("!!!")
        assert not r.is_valid


class TestEUPostprocessor:
    def test_valid_pattern(self):
        r = EUPostprocessor().postprocess("AB123CDE")
        assert r.is_valid

    def test_valid_second_pattern(self):
        r = EUPostprocessor().postprocess("ABC1234D")
        assert r.is_valid

    def test_confusion_fix(self):
        r = EUPostprocessor().postprocess("AB123CDE".replace("0", "O"))
        assert r.is_valid

    def test_garbage_stays_invalid(self):
        r = EUPostprocessor().postprocess("!!!")
        assert not r.is_valid


def _fuser_without_models() -> OCRFuser:
    """Build OCRFuser without loading Paddle/CRNN weights."""
    return OCRFuser.__new__(OCRFuser)


def _ocr(text: str, conf: float) -> list[OCRResult]:
    return [OCRResult(char=c, confidence=conf) for c in text]


class TestOCRFuser:
    def test_agreement_uses_higher_confidence(self):
        f = _fuser_without_models()
        out = f._fuse_results(_ocr("AB12", 0.9), _ocr("AB12", 0.8))
        assert out.plate_text == "AB12"
        assert out.plate_confidence == pytest.approx(0.9)
        assert out.backend_a == "paddle" and out.backend_b == "crnn"

    def test_disagreement_uses_higher_confidence_char(self):
        f = _fuser_without_models()
        a = [OCRResult(char="A", confidence=0.95), OCRResult(char="B", confidence=0.5)]
        b = [OCRResult(char="X", confidence=0.4), OCRResult(char="B", confidence=0.9)]
        out = f._fuse_results(a, b)
        assert out.plate_text == "AB"

    def test_unequal_lengths_padded(self):
        f = _fuser_without_models()
        out = f._fuse_results(_ocr("ABC", 0.9), _ocr("AB", 0.9))
        assert out.plate_text == "ABC"

    def test_only_b_has_result(self):
        f = _fuser_without_models()
        out = f._fuse_results([], _ocr("XY", 0.7))
        assert out.plate_text == "XY"
        assert out.plate_confidence == pytest.approx(0.7)

    def test_empty_both(self):
        f = _fuser_without_models()
        out = f._fuse_results([], [])
        assert out.plate_text == ""
        assert out.plate_confidence == 0.0

    def test_recognize_empty_crop_short_circuits(self):
        f = _fuser_without_models()
        out = f.recognize(np.zeros((0, 0, 3), dtype=np.uint8))
        assert isinstance(out, FusedOCRResult)
        assert out.plate_text == ""

    def test_repr(self):
        f = _fuser_without_models()
        f.paddle = "p"
        f.crnn = "c"
        assert repr(f) == "OCRFuser(A=p, B=c)"


class TestApiCrypto:
    def test_roundtrip(self, monkeypatch):
        import api.crypto as crypto_mod

        key = Fernet.generate_key().decode()
        monkeypatch.setattr(crypto_mod.settings, "celery_encryption_key", key)
        monkeypatch.setattr(crypto_mod, "_cipher", None)
        token = crypto_mod.encrypt_frame(b"frame-bytes")
        assert crypto_mod.decrypt_frame(token) == b"frame-bytes"

    def test_invalid_key_raises_at_use_time(self, monkeypatch):
        import api.crypto as crypto_mod

        monkeypatch.setattr(crypto_mod.settings, "celery_encryption_key", "not-a-valid-key")
        monkeypatch.setattr(crypto_mod, "_cipher", None)
        with pytest.raises(ValueError, match="not a valid Fernet key"):
            crypto_mod.encrypt_frame(b"x")


class TestSecurityEncryptionHelpers:
    def test_encrypt_decrypt_roundtrip(self):
        from api.security import (
            decrypt_data,
            encrypt_data,
            generate_encryption_key,
        )

        key = generate_encryption_key()
        assert isinstance(key, bytes)
        token = encrypt_data(b"secret payload", key)
        assert decrypt_data(token, key) == b"secret payload"

    def test_encrypt_empty_raises(self):
        from api.security import encrypt_data, generate_encryption_key

        with pytest.raises(ValueError, match="cannot be empty"):
            encrypt_data(b"", generate_encryption_key())

    def test_decrypt_empty_raises(self):
        from api.security import decrypt_data, generate_encryption_key

        with pytest.raises(ValueError, match="cannot be empty"):
            decrypt_data(b"", generate_encryption_key())

    def test_decrypt_bad_key_raises(self):
        from api.security import decrypt_data, encrypt_data, generate_encryption_key

        token = encrypt_data(b"data", generate_encryption_key())
        with pytest.raises(ValueError, match="Decryption failed"):
            decrypt_data(token, generate_encryption_key())

    def test_encrypt_bad_key_raises(self):
        from api.security import encrypt_data

        with pytest.raises(ValueError, match="Encryption failed"):
            encrypt_data(b"data", b"bad-key")


class TestPlateTracker:
    def test_empty_detections(self):
        from anpr_core.tracking.bytetrack_wrapper import PlateTracker

        t = PlateTracker()
        out = t.update(np.zeros((0, 4), dtype=np.float32), np.zeros((0,), dtype=np.float32))
        assert out == {}
        assert t.frame_counter == 1

    def test_single_detection_tracked(self):
        from anpr_core.tracking.bytetrack_wrapper import PlateTracker

        t = PlateTracker()
        boxes = np.array([[10.0, 10.0, 100.0, 50.0]], dtype=np.float32)
        confs = np.array([0.9], dtype=np.float32)
        out = t.update(boxes, confs, plate_texts=["AB12CD"], char_confidences_list=[[0.9] * 6])
        assert len(out) == 1
        tp = next(iter(out.values()))
        assert tp.plate_text == "AB12CD"
        assert tp.confidence == pytest.approx(0.9)
        assert tp.frame_idx == 0

    def test_track_history_and_reset(self):
        from anpr_core.tracking.bytetrack_wrapper import PlateTracker

        t = PlateTracker()
        boxes = np.array([[10.0, 10.0, 100.0, 50.0]], dtype=np.float32)
        confs = np.array([0.9], dtype=np.float32)
        out1 = t.update(boxes, confs, plate_texts=["AB12CD"])
        tid = next(iter(out1))
        # second frame, slightly moved box -> same track continues
        boxes2 = boxes + 2.0
        t.update(boxes2, confs, plate_texts=["AB12CD"])
        hist = t.get_track_history(tid)
        assert len(hist) == 2
        assert hist[0]["frame_idx"] == 0
        assert t.get_track_history(999999) == []
        t.reset()
        assert t.get_track_history(tid) == []
        assert t.frame_counter == 0

    def test_missing_optional_texts(self):
        from anpr_core.tracking.bytetrack_wrapper import PlateTracker

        t = PlateTracker()
        boxes = np.array([[10.0, 10.0, 100.0, 50.0]], dtype=np.float32)
        confs = np.array([0.9], dtype=np.float32)
        out = t.update(boxes, confs)
        tp = next(iter(out.values()))
        assert tp.plate_text == ""
        assert tp.char_confidences == []


class TestSecurityTokenHelpers:
    def _token(self):
        from api.security import create_access_token

        return create_access_token("user-123", "operator")

    def _signed(self, payload: dict) -> str:
        from jose import jwt as jose_jwt

        from api.config import settings

        base = {"aud": "anpr-api", "iss": "anpr-issuer", "exp": 9999999999}
        base.update(payload)
        return jose_jwt.encode(base, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    def test_verify_token(self):
        from api.security import verify_token

        payload = verify_token(self._token())
        assert payload["user_id"] == "user-123"

    def test_verify_token_invalid(self):
        from api.security import JWTError, verify_token

        with pytest.raises(JWTError):
            verify_token("not.a.token")

    def test_extract_user_id(self):
        from api.security import extract_user_id_from_token

        assert extract_user_id_from_token(self._token()) == "user-123"

    def test_extract_user_id_missing(self):
        from api.security import JWTError, extract_user_id_from_token

        with pytest.raises(JWTError, match="missing user_id"):
            extract_user_id_from_token(self._signed({"role": "viewer"}))

    def test_extract_role(self):
        from api.security import extract_role_from_token

        assert extract_role_from_token(self._token()) == "operator"

    def test_extract_role_missing(self):
        from api.security import JWTError, extract_role_from_token

        with pytest.raises(JWTError, match="missing role"):
            extract_role_from_token(self._signed({"user_id": "u"}))
