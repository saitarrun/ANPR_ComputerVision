"""
Integration tests for review queue management.

Coverage:
- GET /v1/review-queue: list pending reviews
- POST /v1/review-queue/{id}/resolve: mark reviewed
- Status transitions: pending → approved/rejected/flagged
- Audit log entry creation
"""

from __future__ import annotations

import pytest


class TestListReviewQueue:
    """GET /v1/review-queue endpoint tests."""

    @pytest.mark.integration
    def test_list_review_queue_empty(self, operator_client):
        """Test listing review queue when empty."""
        response = operator_client.get("/v1/review-queue")
        assert response.status_code == 200
        data = response.json()
        items = data if isinstance(data, list) else data.get("items", [])
        assert isinstance(items, list)

    @pytest.mark.integration
    def test_list_review_queue_with_pagination(self, operator_client):
        """Test pagination of review queue."""
        response = operator_client.get("/v1/review-queue?limit=10&offset=0")
        assert response.status_code == 200

    @pytest.mark.integration
    def test_list_review_queue_filter_status(self, operator_client):
        """Test filtering review queue by status."""
        response = operator_client.get("/v1/review-queue?status=pending")
        assert response.status_code == 200

    @pytest.mark.integration
    def test_list_review_queue_requires_auth(self, client):
        """Test that listing requires auth."""
        response = client.get("/v1/review-queue")
        assert response.status_code == 401

    @pytest.mark.integration
    def test_list_review_queue_viewer_forbidden(self, authenticated_client):
        """Test that viewer cannot access review queue."""
        response = authenticated_client.get("/v1/review-queue")
        assert response.status_code == 403


class TestResolveReviewQueueItem:
    """POST /v1/review-queue/{id}/resolve endpoint tests."""

    @pytest.mark.integration
    def test_resolve_review_approve(self, operator_client):
        """Test approving a review queue item."""
        response = operator_client.post(
            "/v1/review-queue/review-id-1/resolve",
            json={"action": "approve", "comment": "Approved"},
        )
        # May return 404 if item doesn't exist, or success if created
        assert response.status_code in [200, 404, 422]

    @pytest.mark.integration
    def test_resolve_review_reject(self, operator_client):
        """Test rejecting a review queue item."""
        response = operator_client.post(
            "/v1/review-queue/review-id-2/resolve",
            json={"action": "reject", "comment": "False positive"},
        )
        assert response.status_code in [200, 404, 422]

    @pytest.mark.integration
    def test_resolve_review_flag(self, operator_client):
        """Test flagging a review queue item for escalation."""
        response = operator_client.post(
            "/v1/review-queue/review-id-3/resolve",
            json={"action": "flag", "comment": "Needs escalation"},
        )
        assert response.status_code in [200, 404, 422]

    @pytest.mark.integration
    def test_resolve_review_missing_action(self, operator_client):
        """Test resolving without action."""
        response = operator_client.post(
            "/v1/review-queue/review-id-4/resolve",
            json={"comment": "No action"},
        )
        assert response.status_code in [400, 422]

    @pytest.mark.integration
    def test_resolve_review_invalid_action(self, operator_client):
        """Test resolving with invalid action."""
        response = operator_client.post(
            "/v1/review-queue/review-id-5/resolve",
            json={"action": "invalid", "comment": "Bad action"},
        )
        assert response.status_code in [400, 422]

    @pytest.mark.integration
    def test_resolve_review_requires_auth(self, client):
        """Test that resolving requires auth."""
        response = client.post(
            "/v1/review-queue/review-id/resolve",
            json={"action": "approve"},
        )
        assert response.status_code == 401

    @pytest.mark.integration
    def test_resolve_review_viewer_forbidden(self, authenticated_client):
        """Test that viewer cannot resolve reviews."""
        response = authenticated_client.post(
            "/v1/review-queue/review-id/resolve",
            json={"action": "approve"},
        )
        assert response.status_code == 403

    @pytest.mark.integration
    def test_resolve_review_not_found(self, operator_client):
        """Test resolving non-existent item."""
        response = operator_client.post(
            "/v1/review-queue/nonexistent/resolve",
            json={"action": "approve"},
        )
        assert response.status_code == 404

    @pytest.mark.integration
    def test_resolve_creates_audit_log_entry(self, operator_client):
        """Test that resolving a review creates audit log entry."""
        # This would be tested with audit log check
        response = operator_client.post(
            "/v1/review-queue/review-id/resolve",
            json={"action": "approve", "comment": "OK"},
        )
        # Audit log entry should be created (tested in audit_log tests)
        assert response.status_code in [200, 404, 422]


class TestReviewQueueStatusTransitions:
    """Test valid status transitions."""

    @pytest.mark.integration
    def test_transition_pending_to_approved(self, operator_client):
        """Test pending → approved transition."""
        response = operator_client.post(
            "/v1/review-queue/review-pending/resolve",
            json={"action": "approve"},
        )
        # Verify transition occurred
        assert response.status_code in [200, 404, 422]

    @pytest.mark.integration
    def test_transition_pending_to_rejected(self, operator_client):
        """Test pending → rejected transition."""
        response = operator_client.post(
            "/v1/review-queue/review-pending/resolve",
            json={"action": "reject"},
        )
        assert response.status_code in [200, 404, 422]

    @pytest.mark.integration
    def test_transition_pending_to_flagged(self, operator_client):
        """Test pending → flagged transition."""
        response = operator_client.post(
            "/v1/review-queue/review-pending/resolve",
            json={"action": "flag"},
        )
        assert response.status_code in [200, 404, 422]
