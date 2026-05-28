import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { RegionResponse, CameraResponse } from '../lib/api';
import { regionsAPI, camerasAPI, getWSUrl } from '../lib/api';
import { useAuthStore } from '../stores/authStore';

export const LivePage = () => {
  const user = useAuthStore((state) => state.user);
  const [selectedRegionId, setSelectedRegionId] = useState<number | null>(null);
  const [selectedCameraId, setSelectedCameraId] = useState<number | null>(null);
  const [wsStatus, setWsStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected');
  const [detectionCount, setDetectionCount] = useState(0);

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
      const response = await camerasAPI.list(selectedRegionId);
      return response.data;
    },
    enabled: selectedRegionId !== null,
  });

  // Initialize WebSocket when camera is selected
  useEffect(() => {
    if (!selectedCameraId || !user?.id) return;

    const token = localStorage.getItem('access_token');
    if (!token) return;

    const streamId = `camera-${selectedCameraId}`;
    const wsUrl = getWSUrl(streamId, token);

    setWsStatus('connecting');
    const ws = new WebSocket(wsUrl);

    const handleOpen = () => {
      setWsStatus('connected');
      setDetectionCount(0);
    };

    const handleMessage = (event: MessageEvent) => {
      try {
        JSON.parse(event.data);
        setDetectionCount((c) => c + 1);
        // TODO: Update frame display with detection payload
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    const handleClose = () => {
      setWsStatus('disconnected');
    };

    const handleError = (event: Event) => {
      console.error('WebSocket error:', event);
      setWsStatus('disconnected');
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
  }, [selectedCameraId, user?.id]);

  const handleRegionChange = (regionId: number) => {
    setSelectedRegionId(regionId);
    setSelectedCameraId(null);
  };

  const handleCameraChange = (cameraId: number) => {
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
              onChange={(e) => handleRegionChange(Number(e.target.value))}
              disabled={regionsLoading}
              className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 disabled:opacity-50"
              data-testid="region-select"
            >
              <option value="">-- Select Region --</option>
              {regions.map((region) => (
                <option key={region.id} value={region.id}>
                  {region.code} {region.id}
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
              onChange={(e) => handleCameraChange(Number(e.target.value))}
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
              {detectionCount}
            </div>
          </div>
        </div>

        {/* Video Stream Area */}
        <div className="lg:col-span-3">
          <div className="aspect-video bg-slate-900 dark:bg-slate-900 rounded-lg border border-slate-300 dark:border-slate-700 flex items-center justify-center">
            {selectedCameraId ? (
              <div className="text-center text-slate-400">
                <div className="text-6xl mb-4">📹</div>
                <p className="text-sm">Video stream placeholder</p>
                <p className="text-xs text-slate-500 mt-2">
                  WebSocket connected to camera-{selectedCameraId}
                </p>
              </div>
            ) : (
              <div className="text-center text-slate-500">
                <div className="text-6xl mb-4">🎥</div>
                <p className="text-sm">Select a region and camera to start</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
