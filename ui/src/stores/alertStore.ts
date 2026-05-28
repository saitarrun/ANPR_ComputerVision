import { create } from 'zustand';

export interface Alert {
  id: string;
  watchlist_id: string;
  plate_id: string;
  plate_string: string;
  region: string;
  timestamp: number;
}

interface AlertState {
  alerts: Alert[];
  unreadCount: number;
  addAlert: (alert: Alert) => void;
  dismissAlert: (id: string) => void;
  clearAlerts: () => void;
  markAsRead: () => void;
}

export const useAlertStore = create<AlertState>((set) => ({
  alerts: [],
  unreadCount: 0,

  addAlert: (alert: Alert) =>
    set((state) => ({
      alerts: [alert, ...state.alerts].slice(0, 50),
      unreadCount: state.unreadCount + 1,
    })),

  dismissAlert: (id: string) =>
    set((state) => ({
      alerts: state.alerts.filter((a) => a.id !== id),
    })),

  clearAlerts: () =>
    set({ alerts: [], unreadCount: 0 }),

  markAsRead: () =>
    set({ unreadCount: 0 }),
}));
