import { useState, useLayoutEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { RegionResponse, CameraResponse } from '../lib/api';
import { regionsAPI, camerasAPI, getWSUrl } from '../lib/api';
import { useAuthStore } from '../stores/authStore';
import { useDetectionStore, type Detection } from '../stores/detectionStore';

export const LivePage = () => {
  const user = useAuthStore((state) => state.user);
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null);
  const [selectedCameraId, setSelectedCameraId] = useState<string | null>(null);
  const [wsStatus, setWsStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected');

  const detections = useDetectionStore((state) => state.detections);
  const addDetection = useDetectionStore((state) => state.addDetection);
  const setConnected = useDetectionStore((state) => state.setConnected);

  // Fetch regions
  const { data: regions = [], isLoading: regionsLoading } = useQuery<RegionResponse[]>({
    queryKey: ['regions'],
    queryFn: async () => {
      const response = await regionsAPI.list();
      return response.data;
    },
    staleTime: Infinity,
  });

  // Fetch cameras for selected region
  const { data: cameras = [], isLoading: camerasLoading } = useQuery<CameraResponse[]>({
    queryKey: ['cameras', selectedRegionId],
    queryFn: async () => {
      if (!selectedRegionId) return [];
      const response = await camerasAPI.listByRegion(selectedRegionId);
      return response.data;
    },
    enabled: selectedRegionId !== null,
  });

  // Initialize WebSocket when camera is selected
  useLayoutEffect(() => {
    if (!selectedCameraId || !user?.id) return;

    const token = localStorage.getItem('access_token');
    if (!token) return;

    const streamId = `camera-${selectedCameraId}`;
    const wsUrl = getWSUrl(streamId, token);

    // eslint-disable-next-line react-hooks/set-state-in-effect
    setWsStatus('connecting');
    setConnected(false);
    const ws = new WebSocket(wsUrl);

    const handleOpen = () => {
      setWsStatus('connected');
      setConnected(true);
    };

    const handleMessage = (event: MessageEvent) => {
      try {
        const detection: Detection = JSON.parse(event.data);
        addDetection(detection);
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    const handleClose = () => {
      setWsStatus('disconnected');
      setConnected(false);
    };

    const handleError = (event: Event) => {
      console.error('WebSocket error:', event);
      setWsStatus('disconnected');
      setConnected(false);
    };

    ws.addEventListener('open', handleOpen);
    ws.addEventListener('message', handleMessage);
    ws.addEventListener('close', handleClose);
    ws.addEventListener('error', handleError);

    return () => {
      ws.removeEventListener('open', handleOpen);
      ws.removeEventListener('message', handleMessage);
      ws.removeEventListener('close', handleClose);
      ws.removeEventListener('error', handleError);
      ws.close();
    };
  }, [selectedCameraId, user?.id, addDetection, setConnected]);

  const handleRegionChange = (regionId: string) => {
    setSelectedRegionId(regionId);
    setSelectedCameraId(null);
  };

  const handleCameraChange = (cameraId: string) => {
    setSelectedCameraId(cameraId);
  };

  return (
    <div className="p-8">
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Region/Camera Selection */}
        <div className="lg:col-span-1 space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
              Region
            </label>
            <select
              value={selectedRegionId ?? ''}
              onChange={(e) => handleRegionChange(e.target.value)}
              disabled={regionsLoading}
              className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 disabled:opacity-50"
              data-testid="region-select"
            >
              <option value="">-- Select Region --</option>
              {regions.map((region) => (
                <option key={region.id} value={region.id}>
                  {region.code}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
              Camera
            </label>
            <select
              value={selectedCameraId ?? ''}
              onChange={(e) => handleCameraChange(e.target.value)}
              disabled={camerasLoading || !selectedRegionId}
              className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 disabled:opacity-50"
              data-testid="camera-select"
            >
              <option value="">-- Select Camera --</option>
              {cameras.map((camera) => (
                <option key={camera.id} value={camera.id}>
                  {camera.name} ({camera.status})
                </option>
              ))}
            </select>
          </div>

          {/* Connection Status */}
          <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
            <div className="text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
              WebSocket Status
            </div>
            <div className="flex items-center gap-2">
              <div
                className={`w-3 h-3 rounded-full ${
                  wsStatus === 'connected'
                    ? 'bg-green-500'
                    : wsStatus === 'connecting'
                      ? 'bg-yellow-500'
                      : 'bg-red-500'
                }`}
              />
              <span className="text-sm text-slate-600 dark:text-slate-400 capitalize">
                {wsStatus}
              </span>
            </div>
          </div>

          {/* Stats */}
          <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
            <div className="text-xs font-medium text-slate-700 dark:text-slate-300 mb-2">
              Detections This Session
            </div>
            <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">
              {detections.length}
            </div>
          </div>
        </div>

        {/* Detection Grid Area */}
        <div className="lg:col-span-3">
          <div className="space-y-4">
            <div>
              <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-3">
                Real-time Detections
              </h3>
              {detections.length === 0 ? (
                <div className="text-center py-12 text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-800 rounded-lg">
                  {selectedCameraId ? 'Waiting for detections...' : 'Select a camera to begin'}
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-3 max-h-96 overflow-y-auto">
                  {detections.slice(0, 20).map((detection) => (
                    <div
                      key={detection.id}
                      className="p-3 bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900 dark:to-blue-800 rounded-lg border border-blue-200 dark:border-blue-700 hover:shadow-md transition-shadow"
                      data-testid={`detection-card-${detection.id}`}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div className="text-xs font-mono font-bold text-blue-900 dark:text-blue-100">
                          {detection.plate_id.substring(0, 8)}...
                        </div>
                        <div className="text-xs px-2 py-1 bg-blue-600 text-white rounded-full font-medium">
                          {(detection.confidence * 100).toFixed(0)}%
                        </div>
                      </div>
                      <div className="text-xs text-slate-600 dark:text-slate-400 space-y-1">
                        <div>OCR: {detection.ocr_backend}</div>
                        <div>Quality: {(detection.quality_score * 100).toFixed(0)}%</div>
                        <div className="text-xs text-slate-500 dark:text-slate-500">
                          {new Date(detection.frame_timestamp).toLocaleTimeString()}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
