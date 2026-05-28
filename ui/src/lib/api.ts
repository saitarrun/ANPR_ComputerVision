import axios from 'axios';
import type { AxiosInstance } from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach token to every request
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 responses
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// API types
export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserResponse {
  id: string;
  email: string;
  username: string;
  role: 'viewer' | 'operator' | 'admin';
}

export interface RegionResponse {
  id: string;
  code: string;
  name: string;
  regex: string;
  charset: string;
  retention_days: number;
  created_at: string;
  updated_at: string;
}

export interface CameraResponse {
  id: string;
  name: string;
  source_type: string;
  url?: string;
  region_id: string;
  latitude?: number;
  longitude?: number;
  status: 'active' | 'inactive' | 'error';
  last_heartbeat?: string;
  created_at: string;
  updated_at: string;
}

export interface DetectionResponse {
  id: string;
  camera_id: string;
  plate_id: string;
  frame_timestamp: string;
  confidence: number;
  bbox: Record<string, number>;
  ocr_backend: string;
  quality_score: number;
  crop_url?: string;
  frame_url?: string;
  is_persisted: string;
  tracking_id?: string;
  created_at: string;
  updated_at: string;
}

export interface PlateResponse {
  id: string;
  plate_string: string;
  region_id: string;
  detection_count: number;
  first_seen_at: string;
  last_seen_at: string;
  avg_confidence: number;
  created_at: string;
  updated_at: string;
}

export interface WatchlistResponse {
  id: string;
  plate_pattern: string;
  region_id: string;
  reason?: string;
  priority: number;
  alert_enabled: boolean;
  alert_channel: 'webhook' | 'email' | 'sms';
  dedup_window: number;
  last_hit?: string;
  hit_count: number;
  created_by_user_id: string;
  created_at: string;
  updated_at: string;
}

export interface ReviewQueueResponse {
  id: string;
  detection_id: string;
  status: 'pending' | 'approved' | 'rejected' | 'flagged';
  reviewer_id?: string;
  detection_blob: Record<string, unknown>;
  notes?: string;
  created_at: string;
  updated_at: string;
}

export interface AuditLogResponse {
  id: string;
  user_id: string;
  action: string;
  resource_type: string;
  resource_id: string;
  ip_address: string;
  details: Record<string, unknown>;
  created_at: string;
}

// API endpoints
export const authAPI = {
  login: (data: LoginRequest) =>
    apiClient.post<TokenResponse>('/v1/auth/login', data),
  refresh: () =>
    apiClient.post<TokenResponse>('/v1/auth/refresh', {}),
  me: () =>
    apiClient.get<UserResponse>('/v1/auth/me'),
};

export const camerasAPI = {
  listByRegion: (regionId: string) =>
    apiClient.get<CameraResponse[]>(`/v1/regions/${regionId}/cameras`),
  get: (id: string) =>
    apiClient.get<CameraResponse>(`/v1/cameras/${id}`),
};

export const regionsAPI = {
  list: () =>
    apiClient.get<RegionResponse[]>('/v1/regions'),
  get: (id: string) =>
    apiClient.get<RegionResponse>(`/v1/regions/${id}`),
};

export const platesAPI = {
  list: (filters?: { region_id?: string; limit?: number }) =>
    apiClient.get<PlateResponse[]>('/v1/plates', { params: filters }),
  get: (id: string) =>
    apiClient.get<PlateResponse>(`/v1/plates/${id}`),
};

export const detectionAPI = {
  list: (filters?: { region_id?: string; camera_id?: string; limit?: number }) =>
    apiClient.get<DetectionResponse[]>('/v1/detections', { params: filters }),
  get: (id: string) =>
    apiClient.get<DetectionResponse>(`/v1/detections/${id}`),
};

export const watchlistAPI = {
  create: (data: { plate_pattern: string; region_id: string; reason?: string; priority?: number; alert_enabled?: boolean; alert_channel?: string }) =>
    apiClient.post<WatchlistResponse>('/v1/watchlist', data),
  list: (filters?: { region_id?: string; enabled_only?: boolean }) =>
    apiClient.get<WatchlistResponse[]>('/v1/watchlist', { params: filters }),
  get: (id: string) =>
    apiClient.get<WatchlistResponse>(`/v1/watchlist/${id}`),
  update: (id: string, data: { plate_pattern: string; region_id: string; reason?: string; priority?: number; alert_enabled?: boolean; alert_channel?: string }) =>
    apiClient.put<WatchlistResponse>(`/v1/watchlist/${id}`, data),
  delete: (id: string) =>
    apiClient.delete(`/v1/watchlist/${id}`),
};

export const reviewQueueAPI = {
  list: (filters?: { status_filter?: string; confidence_min?: number; confidence_max?: number; region_id?: string; limit?: number }) =>
    apiClient.get<ReviewQueueResponse[]>('/v1/review-queue', { params: filters }),
  resolve: (id: string, data: { status: string; notes?: string; corrected_plate?: string }) =>
    apiClient.post<ReviewQueueResponse>(`/v1/review-queue/${id}/resolve`, data),
  stats: () =>
    apiClient.get<{ pending: number; approved: number; rejected: number; flagged: number; avg_confidence: number }>('/v1/review-queue/stats'),
};

export const auditLogAPI = {
  list: (filters?: { date_from?: string; date_to?: string; user_id_filter?: string; action?: string; resource_type?: string; limit?: number }) =>
    apiClient.get<AuditLogResponse[]>('/v1/audit-log', { params: filters }),
  exportCSV: (filters?: { date_from?: string; date_to?: string; user_id_filter?: string }) =>
    apiClient.get('/v1/audit-log/export/csv', {
      params: filters,
      responseType: 'blob' as const,
    }),
};

export interface UserSettings {
  id: string;
  email: string;
  retention_days: number;
  alert_channels: string[];
  export_redaction_enabled: boolean;
  created_at: string;
  last_login?: string;
}

export interface AdminUser {
  id: string;
  email: string;
  username: string;
  role: 'viewer' | 'operator' | 'admin';
  created_at: string;
  last_login?: string;
  is_active: boolean;
}

export const settingsAPI = {
  changePassword: (data: { current_password: string; new_password: string; confirm_password: string }) =>
    apiClient.post('/v1/auth/change-password', data),
  getSettings: () =>
    apiClient.get<UserSettings>('/v1/settings'),
  updateSettings: (data: { retention_days?: number; alert_channels?: string[]; export_redaction_enabled?: boolean }) =>
    apiClient.put<UserSettings>('/v1/settings', data),
  listUsers: () =>
    apiClient.get<AdminUser[]>('/v1/users'),
  updateUser: (userId: string, data: { role?: string; is_active?: boolean }) =>
    apiClient.put<AdminUser>(`/v1/users/${userId}`, data),
  healthStatus: () =>
    apiClient.get<{ status: string; components: Record<string, string> }>('/v1/health/status'),
};

// WebSocket URL helper
export const getWSUrl = (streamId: string, token: string): string => {
  const wsBase = API_BASE_URL.replace(/^http/, 'ws');
  return `${wsBase}/v1/stream/${streamId}?token=${token}`;
};
