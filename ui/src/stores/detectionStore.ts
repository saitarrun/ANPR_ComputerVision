import { create } from 'zustand';

export interface Detection {
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

interface DetectionState {
  detections: Detection[];
  wsConnected: boolean;
  lastUpdate: number;
  addDetection: (detection: Detection) => void;
  setConnected: (connected: boolean) => void;
  clear: () => void;
}

export const useDetectionStore = create<DetectionState>((set) => ({
  detections: [],
  wsConnected: false,
  lastUpdate: 0,

  addDetection: (detection: Detection) =>
    set((state) => ({
      detections: [detection, ...state.detections].slice(0, 100), // Keep latest 100
      lastUpdate: Date.now(),
    })),

  setConnected: (connected: boolean) =>
    set({ wsConnected: connected }),

  clear: () =>
    set({ detections: [], wsConnected: false, lastUpdate: 0 }),
}));
