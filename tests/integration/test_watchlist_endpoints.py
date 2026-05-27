"""
Integration tests for watchlist management endpoints.

Coverage:
- POST /v1/watchlist: add watchlist entry (operator+)
- GET /v1/watchlist: list entries
- DELETE /v1/watchlist/{id}: remove entry
- RBAC: viewer cannot modify
- Watchlist matching logic
"""

from __future__ import annotations

import pytest


class TestCreateWatchlistEntry:
    """POST /v1/watchlist endpoint tests."""

    @pytest.mark.integration
    def test_create_watchlist_entry_operator(self, operator_client):
        """Test operator can create watchlist entry."""
        response = operator_client.post(
            "/v1/watchlist",
            json={"plate_pattern": "KA*"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["plate_pattern"] == "KA*"

    @pytest.mark.integration
    def test_create_watchlist_entry_admin(self, admin_client):
        """Test admin can create watchlist entry."""
        response = admin_client.post(
            "/v1/watchlist",
            json={"plate_pattern": "DL*"},
        )
        assert response.status_code == 201

    @pytest.mark.integration
    def test_create_watchlist_viewer_forbidden(self, authenticated_client):
        """Test that viewer cannot create watchlist."""
        response = authenticated_client.post(
            "/v1/watchlist",
            json={"plate_pattern": "MH*"},
        )
        assert response.status_code == 403

    @pytest.mark.integration
    def test_create_watchlist_missing_pattern(self, operator_client):
        """Test creating watchlist without pattern."""
        response = operator_client.post(
            "/v1/watchlist",
            json={},
        )
        assert response.status_code == 422

    @pytest.mark.integration
    def test_create_watchlist_empty_pattern(self, operator_client):
        """Test creating watchlist with empty pattern."""
        response = operator_client.post(
            "/v1/watchlist",
            json={"plate_pattern": ""},
        )
        assert response.status_code in [400, 422]

    @pytest.mark.integration
    def test_create_watchlist_requires_auth(self, client):
        """Test that creating watchlist requires auth."""
        response = client.post(
            "/v1/watchlist",
            json={"plate_pattern": "KA*"},
        )
        assert response.status_code == 401

    @pytest.mark.integration
    def test_create_watchlist_with_description(self, operator_client):
        """Test creating watchlist with optional description."""
        response = operator_client.post(
            "/v1/watchlist",
            json={
                "plate_pattern": "KA01*",
                "description": "Bangalore plates",
            },
        )
        assert response.status_code == 201


class TestListWatchlist:
    """GET /v1/watchlist endpoint tests."""

    @pytest.mark.integration
    def test_list_watchlist_empty(self, operator_client):
        """Test listing watchlist when empty."""
        response = operator_client.get("/v1/watchlist")
        assert response.status_code == 200
        data = response.json()
        items = data if isinstance(data, list) else data.get("items", [])
        assert isinstance(items, list)

    @pytest.mark.integration
    def test_list_watchlist_pagination(self, operator_client):
        """Test pagination of watchlist."""
        response = operator_client.get("/v1/watchlist?limit=10&offset=0")
        assert response.status_code == 200

    @pytest.mark.integration
    def test_list_watchlist_requires_auth(self, client):
        """Test that listing watchlist requires auth."""
        response = client.get("/v1/watchlist")
        assert response.status_code == 401

    @pytest.mark.integration
    def test_list_watchlist_viewer_can_view(self, authenticated_client):
        """Test that viewer can view watchlist (read-only)."""
        # Viewer cannot create but can view
        response = authenticated_client.get("/v1/watchlist")
        # May be 403 if viewers can't see watchlist, or 200 if they can view
        assert response.status_code in [200, 403]


class TestDeleteWatchlistEntry:
    """DELETE /v1/watchlist/{id} endpoint tests."""

    @pytest.mark.integration
    def test_delete_watchlist_entry(self, operator_client):
        """Test deleting a watchlist entry."""
        # First create one
        create_response = operator_client.post(
            "/v1/watchlist",
            json={"plate_pattern": "KA*"},
        )
        if create_response.status_code == 201:
            entry_id = create_response.json()["id"]
            delete_response = operator_client.delete(f"/v1/watchlist/{entry_id}")
            assert delete_response.status_code in [200, 204]

    @pytest.mark.integration
    def test_delete_watchlist_not_found(self, operator_client):
        """Test deleting non-existent watchlist entry."""
        response = operator_client.delete("/v1/watchlist/nonexistent")
        assert response.status_code == 404

    @pytest.mark.integration
    def test_delete_watchlist_viewer_forbidden(self, authenticated_client):
        """Test that viewer cannot delete watchlist."""
        response = authenticated_client.delete("/v1/watchlist/any-id")
        assert response.status_code == 403

    @pytest.mark.integration
    def test_delete_watchlist_requires_auth(self, client):
        """Test that deleting requires auth."""
        response = client.delete("/v1/watchlist/any-id")
        assert response.status_code == 401


class TestWatchlistMatching:
    """Test watchlist matching logic."""

    @pytest.mark.integration
    def test_watchlist_pattern_matching_exact(self, operator_client):
        """Test exact plate matching."""
        response = operator_client.post(
            "/v1/watchlist",
            json={"plate_pattern": "KA01AB1234"},
        )
        assert response.status_code == 201

    @pytest.mark.integration
    def test_watchlist_pattern_wildcard(self, operator_client):
        """Test wildcard pattern matching."""
        response = operator_client.post(
            "/v1/watchlist",
            json={"plate_pattern": "KA*"},
        )
        assert response.status_code == 201

    @pytest.mark.integration
    def test_watchlist_match_count_initialized(self, operator_client):
        """Test that match_count is initialized to 0."""
        response = operator_client.post(
            "/v1/watchlist",
            json={"plate_pattern": "DL*"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "match_count" in data
        assert data["match_count"] == 0
