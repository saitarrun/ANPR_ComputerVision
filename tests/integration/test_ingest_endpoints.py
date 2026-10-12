"""Integration tests for the ingest router."""

import pytest


class TestIngestFrame:
    def test_ingest_invalid_base64(self, operator_client):
        r = operator_client.post(
            "/v1/ingest/frame",
            json={
                "stream_id": "test-stream",
                "frame_b64_jpeg": "!!!not-valid-base64!!!",
                "camera_id": "test-camera",
            },
        )
        assert r.status_code == 400

    def test_ingest_requires_auth(self, client):
        r = client.post(
            "/v1/ingest/frame",
            json={
                "stream_id": "s",
                "frame_b64_jpeg": "aGVsbG8=",
                "camera_id": "c",
            },
        )
        assert r.status_code == 401

    def test_ingest_missing_fields(self, operator_client):
        r = operator_client.post("/v1/ingest/frame", json={})
        assert r.status_code == 422

    def test_task_status_not_found(self, operator_client):
        r = operator_client.get("/v1/ingest/task/nonexistent-task-id")
        assert r.status_code in (200, 404)
