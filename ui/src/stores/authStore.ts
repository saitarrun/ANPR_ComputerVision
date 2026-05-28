/* eslint-disable @typescript-eslint/no-explicit-any */
import { create } from 'zustand';
import type { UserResponse } from '../lib/api';
import { authAPI } from '../lib/api';

interface AuthState {
  user: UserResponse | null;
  isLoading: boolean;
  error: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  fetchUser: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isLoading: false,
  error: null,
  isAuthenticated: !!localStorage.getItem('access_token'),

  login: async (email: string, password: string) => {
    set({ isLoading: true, error: null });
    try {
      const response = await authAPI.login({ email, password });
      localStorage.setItem('access_token', response.data.access_token);
      localStorage.setItem('refresh_token', response.data.refresh_token);

      // Fetch user info
      const userResponse = await authAPI.me();
      set({
        user: userResponse.data,
        isAuthenticated: true,
        isLoading: false
      });
    } catch (err: any) {
      set({
        error: err.response?.data?.error?.message || 'Login failed',
        isLoading: false
      });
      throw err;
    }
  },

  logout: () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    set({ user: null, isAuthenticated: false });
  },

  fetchUser: async () => {
    set({ isLoading: true });
    try {
      const response = await authAPI.me();
      set({
        user: response.data,
        isAuthenticated: true,
        isLoading: false
      });
    } catch (err: any) {
      set({
        error: err.response?.data?.error?.message || 'Failed to fetch user',
        isLoading: false,
        isAuthenticated: false
      });
    }
  },
}));
