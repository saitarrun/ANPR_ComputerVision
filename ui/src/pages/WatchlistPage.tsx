/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { RegionResponse, WatchlistResponse } from '../lib/api';
import { regionsAPI, watchlistAPI } from '../lib/api';
import '../styles/WatchlistPage.css';

interface FormData {
  plate_pattern: string;
  region_id: string;
  reason: string;
  alert_enabled: boolean;
  alert_channel: 'webhook' | 'email' | 'sms';
}

const INITIAL_FORM: FormData = {
  plate_pattern: '',
  region_id: '',
  reason: '',
  alert_enabled: true,
  alert_channel: 'webhook',
};

export function WatchlistPage() {
  const queryClient = useQueryClient();
  const [formData, setFormData] = useState<FormData>(INITIAL_FORM);
  const [selectedRegionFilter, setSelectedRegionFilter] = useState<string>('');
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string>('');
  const [editingId, setEditingId] = useState<string | null>(null);

  // Fetch regions
  const { data: regions = [] } = useQuery<RegionResponse[]>({
    queryKey: ['regions'],
    queryFn: async () => {
      const response = await regionsAPI.list();
      return response.data;
    },
    staleTime: Infinity,
  });

  // Fetch watchlist
  const { data: watchlist = [], isLoading } = useQuery<WatchlistResponse[]>({
    queryKey: ['watchlist', selectedRegionFilter],
    queryFn: async () => {
      const response = await watchlistAPI.list(
        selectedRegionFilter ? { region_id: selectedRegionFilter } : undefined
      );
      return response.data;
    },
  });

  // Create mutation
  const createMutation = useMutation({
    mutationFn: async (data: FormData) => {
      const response = await watchlistAPI.create(data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist'] });
      setFormData(INITIAL_FORM);
      setShowForm(false);
      setError('');
    },
    onError: (error: any) => {
      setError(error.response?.data?.detail || 'Failed to create watchlist');
    },
  });

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: async (data: FormData) => {
      if (!editingId) throw new Error('No watchlist selected');
      const response = await watchlistAPI.update(editingId, data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist'] });
      setFormData(INITIAL_FORM);
      setShowForm(false);
      setEditingId(null);
      setError('');
    },
    onError: (error: any) => {
      setError(error.response?.data?.detail || 'Failed to update watchlist');
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await watchlistAPI.delete(id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist'] });
      setError('');
    },
    onError: (error: any) => {
      setError(error.response?.data?.detail || 'Failed to delete watchlist');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!formData.plate_pattern.trim()) {
      setError('Pattern is required');
      return;
    }

    if (!formData.region_id) {
      setError('Region is required');
      return;
    }

    if (editingId) {
      updateMutation.mutate(formData);
    } else {
      createMutation.mutate(formData);
    }
  };

  const handleEdit = (item: WatchlistResponse) => {
    setEditingId(item.id);
    setFormData({
      plate_pattern: item.plate_pattern,
      region_id: item.region_id,
      reason: item.reason || '',
      alert_enabled: item.alert_enabled,
      alert_channel: item.alert_channel,
    });
    setShowForm(true);
  };

  const handleCancel = () => {
    setShowForm(false);
    setEditingId(null);
    setFormData(INITIAL_FORM);
    setError('');
  };

  const getRegionName = (regionId: string) => {
    return regions.find((r) => r.id === regionId)?.name || regionId;
  };

  return (
    <div className="watchlist-page">
      <div className="watchlist-header">
        <h1>Watchlist Patterns</h1>
        <button
          className="btn btn-primary"
          onClick={() => {
            setShowForm(!showForm);
            if (showForm) handleCancel();
          }}
        >
          {showForm ? 'Cancel' : '+ Add Pattern'}
        </button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {showForm && (
        <div className="watchlist-form">
          <h2>{editingId ? 'Edit Pattern' : 'Add New Pattern'}</h2>
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label htmlFor="pattern">Pattern (Regex)</label>
              <input
                id="pattern"
                type="text"
                placeholder="e.g., [0-9]{3}[A-Z]{2}[0-9]{4}"
                value={formData.plate_pattern}
                onChange={(e) =>
                  setFormData({ ...formData, plate_pattern: e.target.value })
                }
                data-testid="pattern-input"
              />
              <small>Use valid regex pattern</small>
            </div>

            <div className="form-group">
              <label htmlFor="region">Region</label>
              <select
                id="region"
                value={formData.region_id}
                onChange={(e) =>
                  setFormData({ ...formData, region_id: e.target.value })
                }
                data-testid="region-select"
              >
                <option value="">-- Select Region --</option>
                {regions.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="reason">Reason</label>
              <input
                id="reason"
                type="text"
                placeholder="Optional reason for watchlist"
                value={formData.reason}
                onChange={(e) =>
                  setFormData({ ...formData, reason: e.target.value })
                }
                data-testid="reason-input"
              />
            </div>

            <div className="form-group">
              <label htmlFor="alert-channel">Alert Channel</label>
              <select
                id="alert-channel"
                value={formData.alert_channel}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    alert_channel: e.target.value as 'webhook' | 'email' | 'sms',
                  })
                }
                data-testid="alert-channel-select"
              >
                <option value="webhook">Webhook</option>
                <option value="email">Email</option>
                <option value="sms">SMS (Stub)</option>
              </select>
            </div>

            <div className="form-group form-group-checkbox">
              <label>
                <input
                  type="checkbox"
                  checked={formData.alert_enabled}
                  onChange={(e) =>
                    setFormData({ ...formData, alert_enabled: e.target.checked })
                  }
                  data-testid="alert-enabled-checkbox"
                />
                Enable Alerts
              </label>
            </div>

            <div className="form-actions">
              <button
                type="submit"
                className="btn btn-primary"
                disabled={
                  createMutation.isPending ||
                  updateMutation.isPending
                }
              >
                {editingId ? 'Update' : 'Create'}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleCancel}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="watchlist-filters">
        <label htmlFor="region-filter">Filter by Region:</label>
        <select
          id="region-filter"
          value={selectedRegionFilter}
          onChange={(e) => setSelectedRegionFilter(e.target.value)}
          data-testid="region-filter"
        >
          <option value="">All Regions</option>
          {regions.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <div className="loading">Loading watchlist...</div>
      ) : watchlist.length === 0 ? (
        <div className="empty-state">
          <p>No watchlist patterns yet.</p>
          <p>Create your first pattern to get started.</p>
        </div>
      ) : (
        <div className="watchlist-table-container">
          <table className="watchlist-table">
            <thead>
              <tr>
                <th>Pattern</th>
                <th>Region</th>
                <th>Alert Channel</th>
                <th>Status</th>
                <th>Last Hit</th>
                <th>Hit Count</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {watchlist.map((item) => (
                <tr key={item.id} data-testid={`watchlist-row-${item.id}`}>
                  <td className="monospace">{item.plate_pattern}</td>
                  <td>{getRegionName(item.region_id)}</td>
                  <td>{item.alert_channel}</td>
                  <td>
                    <span
                      className={`status status-${
                        item.alert_enabled ? 'enabled' : 'disabled'
                      }`}
                    >
                      {item.alert_enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </td>
                  <td>
                    {item.last_hit
                      ? new Date(item.last_hit).toLocaleTimeString()
                      : '-'}
                  </td>
                  <td>{item.hit_count}</td>
                  <td className="actions">
                    <button
                      className="btn btn-sm btn-secondary"
                      onClick={() => handleEdit(item)}
                      data-testid={`edit-btn-${item.id}`}
                    >
                      Edit
                    </button>
                    <button
                      className="btn btn-sm btn-danger"
                      onClick={() => deleteMutation.mutate(item.id)}
                      data-testid={`delete-btn-${item.id}`}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
