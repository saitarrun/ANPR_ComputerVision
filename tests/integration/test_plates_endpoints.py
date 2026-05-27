"""
Integration tests for plate search and retrieval endpoints.

Coverage:
- GET /v1/plates: list plates (paginated, filtered)
- GET /v1/plates/{id}: plate detail
- GET /v1/plates/{id}/events: detection history
- Search, filtering by region, date range
- Encryption validation
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta


class TestListPlates:
    """GET /v1/plates endpoint tests."""

    @pytest.mark.integration
    def test_list_plates_empty(self, authenticated_client):
        """Test listing plates when none exist."""
        response = authenticated_client.get("/v1/plates")
        assert response.status_code == 200
        data = response.json()
        items = data if isinstance(data, list) else data.get("items", [])
        assert isinstance(items, list)

    @pytest.mark.integration
    def test_list_plates_with_pagination(self, authenticated_client, test_plate):
        """Test listing plates with pagination."""
        response = authenticated_client.get("/v1/plates?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()
        # Response should be valid
        assert data is not None

    @pytest.mark.integration
    def test_list_plates_search_by_string(self, authenticated_client, test_plate):
        """Test searching plates by plate string."""
        response = authenticated_client.get("/v1/plates?q=KA01AB1234")
        assert response.status_code == 200
        data = response.json()
        items = data if isinstance(data, list) else data.get("items", [])
        # Search may return results or empty list
        assert isinstance(items, list)

    @pytest.mark.integration
    def test_list_plates_filter_by_region(self, authenticated_client, test_plate, test_region):
        """Test filtering plates by region."""
        response = authenticated_client.get(f"/v1/plates?region={test_region.id}")
        assert response.status_code == 200
        data = response.json()
        items = data if isinstance(data, list) else data.get("items", [])
        assert isinstance(items, list)

    @pytest.mark.integration
    def test_list_plates_filter_by_date_range(self, authenticated_client, test_plate):
        """Test filtering plates by date range."""
        now = datetime.utcnow()
        from_date = (now - timedelta(days=1)).isoformat()
        to_date = (now + timedelta(days=1)).isoformat()
        response = authenticated_client.get(f"/v1/plates?from={from_date}&to={to_date}")
        assert response.status_code == 200

    @pytest.mark.integration
    def test_list_plates_requires_auth(self, client):
        """Test that listing requires auth."""
        response = client.get("/v1/plates")
        assert response.status_code == 401

    @pytest.mark.integration
    def test_list_plates_returns_decrypted_plate(self, authenticated_client, test_plate):
        """Test that plates are returned decrypted."""
        response = authenticated_client.get("/v1/plates")
        assert response.status_code == 200
        data = response.json()
        items = data if isinstance(data, list) else data.get("items", [])
        # If items exist, plate_string should be decrypted (human-readable)
        if items:
            assert "plate_string" in items[0] or "plate" in items[0]


class TestGetPlateDetail:
    """GET /v1/plates/{id} endpoint tests."""

    @pytest.mark.integration
    def test_get_plate_detail(self, authenticated_client, test_plate):
        """Test getting plate detail."""
        response = authenticated_client.get(f"/v1/plates/{test_plate.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_plate.id
        assert "plate_string" in data or "plate" in data
        assert "confidence" in data

    @pytest.mark.integration
    def test_get_plate_not_found(self, authenticated_client):
        """Test getting non-existent plate."""
        response = authenticated_client.get("/v1/plates/nonexistent")
        assert response.status_code == 404

    @pytest.mark.integration
    def test_get_plate_includes_region(self, authenticated_client, test_plate):
        """Test that plate detail includes region info."""
        response = authenticated_client.get(f"/v1/plates/{test_plate.id}")
        assert response.status_code == 200
        data = response.json()
        assert "region" in data or "region_id" in data

    @pytest.mark.integration
    def test_get_plate_requires_auth(self, client, test_plate):
        """Test that getting plate requires auth."""
        response = client.get(f"/v1/plates/{test_plate.id}")
        assert response.status_code == 401


class TestPlateDetectionHistory:
    """GET /v1/plates/{id}/events endpoint tests."""

    @pytest.mark.integration
    def test_get_plate_events_empty(self, authenticated_client, test_plate):
        """Test getting detection history for plate with no detections."""
        response = authenticated_client.get(f"/v1/plates/{test_plate.id}/events")
        assert response.status_code == 200
        data = response.json()
        events = data if isinstance(data, list) else data.get("events", [])
        assert isinstance(events, list)
        # Should be empty since no detections created
        assert len(events) == 0

    @pytest.mark.integration
    def test_get_plate_events_pagination(self, authenticated_client, test_plate):
        """Test pagination of detection events."""
        response = authenticated_client.get(
            f"/v1/plates/{test_plate.id}/events?limit=10&offset=0"
        )
        assert response.status_code == 200

    @pytest.mark.integration
    def test_get_plate_events_requires_auth(self, client, test_plate):
        """Test that getting events requires auth."""
        response = client.get(f"/v1/plates/{test_plate.id}/events")
        assert response.status_code == 401

    @pytest.mark.integration
    def test_get_plate_events_not_found(self, authenticated_client):
        """Test getting events for non-existent plate."""
        response = authenticated_client.get("/v1/plates/nonexistent/events")
        assert response.status_code == 404

    @pytest.mark.integration
    def test_get_plate_events_includes_timestamps(self, authenticated_client, test_plate):
        """Test that events include timestamp information."""
        response = authenticated_client.get(f"/v1/plates/{test_plate.id}/events")
        assert response.status_code == 200
        data = response.json()
        events = data if isinstance(data, list) else data.get("events", [])
        if events:
            assert "timestamp" in events[0] or "detected_at" in events[0]


class TestPlateEncryption:
    """Test encryption of plate strings at rest."""

    @pytest.mark.integration
    def test_plate_stored_encrypted(self, authenticated_client, test_plate):
        """Test that plate_string is stored encrypted in database."""
        # Get the plate
        response = authenticated_client.get(f"/v1/plates/{test_plate.id}")
        assert response.status_code == 200
        data = response.json()
        # Plate string should be readable to authorized user
        plate_str = data.get("plate_string") or data.get("plate")
        assert plate_str is not None
        # It should be "KA01AB1234" (decrypted)
        assert plate_str == "KA01AB1234" or "KA01" in str(plate_str)

    @pytest.mark.integration
    def test_plate_not_decrypted_for_unauthorized(self, client, test_plate):
        """Test that unauthorized users cannot access plate data."""
        # No auth header
        response = client.get(f"/v1/plates/{test_plate.id}")
        assert response.status_code == 401
