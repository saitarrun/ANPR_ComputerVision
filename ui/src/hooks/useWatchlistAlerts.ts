import { useEffect, useRef, useState } from 'react';
import { useAlertStore } from '../stores/alertStore';
import { getWSUrl } from '../lib/api';

export function useWatchlistAlerts(streamId: string, token: string) {
  const { addAlert } = useAlertStore();
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    if (!streamId || !token) return;

    const wsUrl = getWSUrl(streamId, token);
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('WebSocket connected for alerts');
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'detection') {
          const alert = {
            id: data.detection.id || `alert-${Date.now()}`,
            watchlist_id: data.watchlist_id,
            plate_id: data.detection.plate_id,
            plate_string: data.detection.plate_string,
            region: data.region,
            timestamp: Date.now(),
          };
          addAlert(alert);
        }
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setIsConnected(false);
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setIsConnected(false);
    };

    wsRef.current = ws;

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [streamId, token, addAlert]);

  return {
    isConnected,
  };
}
