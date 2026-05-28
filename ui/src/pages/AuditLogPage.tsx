/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { AuditLogResponse } from '../lib/api';
import { auditLogAPI } from '../lib/api';
import '../styles/AuditLogPage.css';

export function AuditLogPage() {
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const [userIdFilter, setUserIdFilter] = useState<string>('');
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc');

  // Fetch audit log
  const { data: logs = [], isLoading } = useQuery<AuditLogResponse[]>({
    queryKey: ['audit-log', dateFrom, dateTo, userIdFilter],
    queryFn: async () => {
      const response = await auditLogAPI.list({
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        user_id_filter: userIdFilter || undefined,
      });
      return response.data.sort((a, b) => {
        const timeA = new Date(a.created_at).getTime();
        const timeB = new Date(b.created_at).getTime();
        return sortOrder === 'desc' ? timeB - timeA : timeA - timeB;
      });
    },
  });

  const handleExportCSV = async () => {
    try {
      const response = await auditLogAPI.exportCSV({
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        user_id_filter: userIdFilter || undefined,
      });

      // Create download link
      const url = window.URL.createObjectURL(response.data as Blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `audit_log_${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(link);
      link.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(link);
    } catch (error) {
      console.error('Failed to export CSV:', error);
    }
  };

  const getActionBadgeColor = (action: string) => {
    if (action.includes('login')) return 'action-auth';
    if (action.includes('create') || action.includes('add')) return 'action-create';
    if (action.includes('delete') || action.includes('remove')) return 'action-delete';
    if (action.includes('export')) return 'action-export';
    return 'action-view';
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleString();
  };

  const truncateJson = (obj: Record<string, any>, maxLength: number = 100) => {
    const str = JSON.stringify(obj);
    return str.length > maxLength ? str.substring(0, maxLength) + '...' : str;
  };

  return (
    <div className="audit-log-page">
      <div className="audit-header">
        <h1>Audit Log</h1>
        <button
          className="btn btn-primary"
          onClick={handleExportCSV}
          data-testid="export-csv-btn"
        >
          📥 Export CSV
        </button>
      </div>

      <div className="audit-filters">
        <div className="filter-group">
          <label htmlFor="date-from">From Date:</label>
          <input
            id="date-from"
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            data-testid="date-from-input"
          />
        </div>

        <div className="filter-group">
          <label htmlFor="date-to">To Date:</label>
          <input
            id="date-to"
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            data-testid="date-to-input"
          />
        </div>

        <div className="filter-group">
          <label htmlFor="user-id-filter">User ID:</label>
          <input
            id="user-id-filter"
            type="text"
            placeholder="Filter by user ID"
            value={userIdFilter}
            onChange={(e) => setUserIdFilter(e.target.value)}
            data-testid="user-id-filter"
          />
        </div>

        <div className="filter-group">
          <label htmlFor="sort-order">Sort Order:</label>
          <select
            id="sort-order"
            value={sortOrder}
            onChange={(e) => setSortOrder(e.target.value as 'desc' | 'asc')}
            data-testid="sort-order-select"
          >
            <option value="desc">Most Recent</option>
            <option value="asc">Oldest First</option>
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="loading">Loading audit log...</div>
      ) : logs.length === 0 ? (
        <div className="empty-state">
          <p>No audit log entries found.</p>
        </div>
      ) : (
        <div className="audit-table-container">
          <table className="audit-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>User ID</th>
                <th>Action</th>
                <th>Resource</th>
                <th>Resource ID</th>
                <th>IP Address</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id} data-testid={`audit-row-${log.id}`}>
                  <td className="timestamp">{formatTimestamp(log.created_at)}</td>
                  <td className="user-id">{log.user_id.substring(0, 8)}...</td>
                  <td>
                    <span className={`action-badge ${getActionBadgeColor(log.action)}`}>
                      {log.action}
                    </span>
                  </td>
                  <td>{log.resource_type}</td>
                  <td className="monospace">{log.resource_id.substring(0, 12)}...</td>
                  <td className="ip-address">{log.ip_address}</td>
                  <td className="details">
                    <details>
                      <summary>Show</summary>
                      <pre>{truncateJson(log.details)}</pre>
                    </details>
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
