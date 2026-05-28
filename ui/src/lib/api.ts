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

// WebSocket URL helper
export const getWSUrl = (streamId: string, token: string): string => {
  const wsBase = API_BASE_URL.replace(/^http/, 'ws');
  return `${wsBase}/v1/stream/${streamId}?token=${token}`;
};
