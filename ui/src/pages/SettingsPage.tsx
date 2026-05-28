import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import type { UserSettings, AdminUser } from '../lib/api';
import { settingsAPI } from '../lib/api';
import { useAuthStore } from '../stores/authStore';
import '../styles/SettingsPage.css';

export function SettingsPage() {
  const user = useAuthStore((state) => state.user);
  const [activeTab, setActiveTab] = useState<'profile' | 'settings' | 'admin'>('profile');
  const [passwordError, setPasswordError] = useState<string>('');
  const [passwordSuccess, setPasswordSuccess] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  // Fetch user settings
  const { data: settings } = useQuery<UserSettings>({
    queryKey: ['settings'],
    queryFn: async () => {
      const response = await settingsAPI.getSettings();
      return response.data;
    },
  });

  // Fetch admin users
  const { data: adminUsers = [] } = useQuery<AdminUser[]>({
    queryKey: ['admin-users'],
    queryFn: async () => {
      if (user?.role !== 'admin') return [];
      const response = await settingsAPI.listUsers();
      return response.data;
    },
    enabled: user?.role === 'admin',
  });

  // Fetch health status
  const { data: healthStatus } = useQuery({
    queryKey: ['health-status'],
    queryFn: async () => {
      const response = await settingsAPI.healthStatus();
      return response.data;
    },
  });

  // Change password mutation
  const changePasswordMutation = useMutation({
    mutationFn: async () => {
      const response = await settingsAPI.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      return response;
    },
    onSuccess: () => {
      setPasswordSuccess(true);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setPasswordError('');
      setTimeout(() => setPasswordSuccess(false), 5000);
    },
    onError: (error: any) => {
      setPasswordError(
        error.response?.data?.detail || 'Failed to change password'
      );
      setPasswordSuccess(false);
    },
  });

  const handleChangePassword = (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError('');

    if (!currentPassword) {
      setPasswordError('Current password is required');
      return;
    }
    if (!newPassword) {
      setPasswordError('New password is required');
      return;
    }
    if (newPassword.length < 8) {
      setPasswordError('New password must be at least 8 characters');
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError('Passwords do not match');
      return;
    }

    changePasswordMutation.mutate();
  };

  const isAdmin = user?.role === 'admin';

  return (
    <div className="settings-page">
      <div className="settings-header">
        <h1>Settings</h1>
      </div>

      <div className="settings-tabs">
        <button
          className={`tab ${activeTab === 'profile' ? 'active' : ''}`}
          onClick={() => setActiveTab('profile')}
          data-testid="tab-profile"
        >
          Profile
        </button>
        <button
          className={`tab ${activeTab === 'settings' ? 'active' : ''}`}
          onClick={() => setActiveTab('settings')}
          data-testid="tab-settings"
        >
          Preferences
        </button>
        {isAdmin && (
          <button
            className={`tab ${activeTab === 'admin' ? 'active' : ''}`}
            onClick={() => setActiveTab('admin')}
            data-testid="tab-admin"
          >
            Admin
          </button>
        )}
      </div>

      {/* Profile Tab */}
      {activeTab === 'profile' && (
        <div className="tab-content">
          <div className="card">
            <h2>User Profile</h2>
            {user && (
              <div className="profile-info">
                <div className="info-group">
                  <label>Email</label>
                  <div className="info-value">{user.email}</div>
                </div>
                <div className="info-group">
                  <label>Username</label>
                  <div className="info-value">{user.username}</div>
                </div>
                <div className="info-group">
                  <label>Role</label>
                  <div className="info-value">{user.role}</div>
                </div>
              </div>
            )}
          </div>

          <div className="card">
            <h2>Change Password</h2>
            {passwordSuccess && (
              <div className="alert alert-success">
                Password changed successfully!
              </div>
            )}
            {passwordError && (
              <div className="alert alert-error">{passwordError}</div>
            )}
            <form onSubmit={handleChangePassword} className="password-form">
              <div className="form-group">
                <label htmlFor="current-password">Current Password</label>
                <input
                  id="current-password"
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  data-testid="current-password-input"
                />
              </div>

              <div className="form-group">
                <label htmlFor="new-password">New Password</label>
                <input
                  id="new-password"
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  data-testid="new-password-input"
                />
                <small>At least 8 characters</small>
              </div>

              <div className="form-group">
                <label htmlFor="confirm-password">Confirm Password</label>
                <input
                  id="confirm-password"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  data-testid="confirm-password-input"
                />
              </div>

              <button
                type="submit"
                className="btn btn-primary"
                disabled={changePasswordMutation.isPending}
                data-testid="change-password-btn"
              >
                Change Password
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Settings Tab */}
      {activeTab === 'settings' && (
        <div className="tab-content">
          <div className="card">
            <h2>Data Retention</h2>
            {settings && (
              <div className="settings-group">
                <div className="setting-item">
                  <label>Retention Days</label>
                  <div className="setting-value">{settings.retention_days} days</div>
                  <small>GDPR-compliant data retention period</small>
                </div>
              </div>
            )}
          </div>

          <div className="card">
            <h2>Alert Channels</h2>
            {settings && (
              <div className="settings-group">
                <div className="setting-item">
                  <label>Default Channels</label>
                  <div className="channels-list">
                    {settings.alert_channels.map((channel) => (
                      <span key={channel} className="channel-badge">
                        {channel}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="card">
            <h2>Privacy</h2>
            {settings && (
              <div className="settings-group">
                <div className="setting-item">
                  <label>
                    <input
                      type="checkbox"
                      checked={settings.export_redaction_enabled}
                      disabled
                    />
                    Redact Sensitive Data on Export
                  </label>
                  <small>Blur faces and plates when exporting data</small>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Admin Tab */}
      {activeTab === 'admin' && isAdmin && (
        <div className="tab-content">
          <div className="card">
            <h2>System Health</h2>
            {healthStatus && (
              <div className="health-status">
                <div className="status-item">
                  <span className="status-name">Overall Status</span>
                  <span
                    className={`status-badge ${
                      healthStatus.status === 'ok' ? 'ok' : 'degraded'
                    }`}
                  >
                    {healthStatus.status.toUpperCase()}
                  </span>
                </div>
                <div className="components">
                  <h3>Components</h3>
                  {Object.entries(healthStatus.components).map(
                    ([component, status]) => (
                      <div key={component} className="component-item">
                        <span>{component}</span>
                        <span
                          className={`status-badge ${
                            status === 'healthy'
                              ? 'ok'
                              : status === 'unknown'
                              ? 'unknown'
                              : 'error'
                          }`}
                        >
                          {status}
                        </span>
                      </div>
                    )
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="card">
            <h2>User Management</h2>
            {adminUsers.length > 0 ? (
              <div className="users-table-container">
                <table className="users-table">
                  <thead>
                    <tr>
                      <th>Email</th>
                      <th>Username</th>
                      <th>Role</th>
                      <th>Created</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {adminUsers.map((adminUser) => (
                      <tr
                        key={adminUser.id}
                        data-testid={`user-row-${adminUser.id}`}
                      >
                        <td>{adminUser.email}</td>
                        <td>{adminUser.username}</td>
                        <td>{adminUser.role}</td>
                        <td>
                          {new Date(adminUser.created_at).toLocaleDateString()}
                        </td>
                        <td>
                          <span
                            className={`status-badge ${
                              adminUser.is_active ? 'ok' : 'error'
                            }`}
                          >
                            {adminUser.is_active ? 'Active' : 'Inactive'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty-state">No users found</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
