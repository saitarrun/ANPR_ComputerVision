/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { ReviewQueueResponse } from '../lib/api';
import { reviewQueueAPI } from '../lib/api';
import '../styles/ReviewQueuePage.css';

export function ReviewQueuePage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>('pending');
  const [confidenceMin, setConfidenceMin] = useState<number>(0);
  const [confidenceMax, setConfidenceMax] = useState<number>(1);
  const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string>('');

  // Fetch review queue
  const { data: items = [], isLoading } = useQuery<ReviewQueueResponse[]>({
    queryKey: ['review-queue', statusFilter, confidenceMin, confidenceMax],
    queryFn: async () => {
      const response = await reviewQueueAPI.list({
        status_filter: statusFilter || undefined,
        confidence_min: confidenceMin,
        confidence_max: confidenceMax,
      });
      return response.data;
    },
  });

  // Fetch stats
  const { data: stats } = useQuery({
    queryKey: ['review-queue-stats'],
    queryFn: async () => {
      const response = await reviewQueueAPI.stats();
      return response.data;
    },
  });

  // Resolve mutation
  const resolveMutation = useMutation({
    mutationFn: async (data: {
      id: string;
      status: string;
      notes?: string;
      corrected_plate?: string;
    }) => {
      const response = await reviewQueueAPI.resolve(data.id, {
        status: data.status,
        notes: data.notes,
        corrected_plate: data.corrected_plate,
      });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['review-queue'] });
      queryClient.invalidateQueries({ queryKey: ['review-queue-stats'] });
      setError('');
    },
    onError: (error: any) => {
      setError(error.response?.data?.detail || 'Failed to resolve review item');
    },
  });

  const handleResolve = (itemId: string, status: string, notes?: string) => {
    resolveMutation.mutate({
      id: itemId,
      status,
      notes,
    });
  };

  const handleBulkAction = (action: string) => {
    selectedItems.forEach((itemId) => {
      handleResolve(itemId, action);
    });
    setSelectedItems(new Set());
  };

  const toggleItemSelection = (itemId: string) => {
    const newSelection = new Set(selectedItems);
    if (newSelection.has(itemId)) {
      newSelection.delete(itemId);
    } else {
      newSelection.add(itemId);
    }
    setSelectedItems(newSelection);
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.9) return 'confidence-high';
    if (confidence >= 0.7) return 'confidence-medium';
    return 'confidence-low';
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString();
  };

  return (
    <div className="review-queue-page">
      <div className="review-header">
        <h1>Review Queue</h1>
        {stats && (
          <div className="stats">
            <span className="stat-item">
              <strong>{stats.pending}</strong> Pending
            </span>
            <span className="stat-item">
              <strong>{stats.approved}</strong> Approved
            </span>
            <span className="stat-item">
              <strong>{stats.rejected}</strong> Rejected
            </span>
            <span className="stat-item">
              <strong>{stats.flagged}</strong> Flagged
            </span>
            <span className="stat-item">
              Avg Confidence: <strong>{(stats.avg_confidence * 100).toFixed(1)}%</strong>
            </span>
          </div>
        )}
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="review-filters">
        <div className="filter-group">
          <label htmlFor="status-filter">Status:</label>
          <select
            id="status-filter"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            data-testid="status-filter"
          >
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="flagged">Flagged</option>
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="confidence-min">Min Confidence:</label>
          <input
            id="confidence-min"
            type="range"
            min="0"
            max="1"
            step="0.1"
            value={confidenceMin}
            onChange={(e) => setConfidenceMin(parseFloat(e.target.value))}
            data-testid="confidence-min"
          />
          <span>{(confidenceMin * 100).toFixed(0)}%</span>
        </div>

        <div className="filter-group">
          <label htmlFor="confidence-max">Max Confidence:</label>
          <input
            id="confidence-max"
            type="range"
            min="0"
            max="1"
            step="0.1"
            value={confidenceMax}
            onChange={(e) => setConfidenceMax(parseFloat(e.target.value))}
            data-testid="confidence-max"
          />
          <span>{(confidenceMax * 100).toFixed(0)}%</span>
        </div>
      </div>

      {selectedItems.size > 0 && (
        <div className="bulk-actions">
          <span>{selectedItems.size} selected</span>
          <button
            className="btn btn-sm btn-success"
            onClick={() => handleBulkAction('approved')}
          >
            Approve All
          </button>
          <button
            className="btn btn-sm btn-danger"
            onClick={() => handleBulkAction('rejected')}
          >
            Reject All
          </button>
        </div>
      )}

      {isLoading ? (
        <div className="loading">Loading review queue...</div>
      ) : items.length === 0 ? (
        <div className="empty-state">
          <p>No items in review queue.</p>
          <p>All detections are high-confidence!</p>
        </div>
      ) : (
        <div className="review-grid">
          {items.map((item) => {
            const blob = (item.detection_blob || {}) as Record<string, unknown>;
            const confidence = (blob.confidence as number) || 0;
            const plateName = (blob.plate_string as string) || 'Unknown';
            const ocrBackend = (blob.ocr_backend as string) || '-';

            return (
              <div
                key={item.id}
                className="review-card"
                data-testid={`review-card-${item.id}`}
              >
                <div className="card-checkbox">
                  <input
                    type="checkbox"
                    checked={selectedItems.has(item.id)}
                    onChange={() => toggleItemSelection(item.id)}
                    data-testid={`checkbox-${item.id}`}
                  />
                </div>

                <div className="card-image">
                  {(blob.crop_url as string) ? (
                    <img
                      src={blob.crop_url as string}
                      alt={plateName}
                      className="plate-crop"
                    />
                  ) : (
                    <div className="image-placeholder">No Image</div>
                  )}
                </div>

                <div className="card-content">
                  <div className="plate-string">{plateName}</div>
                  <div className="card-meta">
                    <span className={`confidence ${getConfidenceColor(confidence)}`}>
                      {(confidence * 100).toFixed(0)}%
                    </span>
                    <span className="ocr-backend">{ocrBackend}</span>
                  </div>
                  <div className="timestamp">{formatTimestamp(item.created_at)}</div>
                </div>

                <div className="card-actions">
                  <button
                    className="btn btn-sm btn-success"
                    onClick={() => handleResolve(item.id, 'approved')}
                    disabled={resolveMutation.isPending}
                    data-testid={`approve-btn-${item.id}`}
                  >
                    ✓ Approve
                  </button>
                  <button
                    className="btn btn-sm btn-danger"
                    onClick={() => handleResolve(item.id, 'rejected')}
                    disabled={resolveMutation.isPending}
                    data-testid={`reject-btn-${item.id}`}
                  >
                    ✕ Reject
                  </button>
                  <button
                    className="btn btn-sm btn-warning"
                    onClick={() => {
                      const corrected = prompt('Enter corrected plate:');
                      if (corrected) {
                        handleResolve(item.id, 'flagged', corrected);
                      }
                    }}
                    disabled={resolveMutation.isPending}
                    data-testid={`flag-btn-${item.id}`}
                  >
                    🚩 Flag
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
