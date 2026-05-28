import { useLayoutEffect, useState, useRef } from 'react';
import { useAlertStore } from '../stores/alertStore';
import '../styles/AlertNotification.css';

export function AlertNotification() {
  const { alerts, dismissAlert } = useAlertStore();
  const [visible, setVisible] = useState<string | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  useLayoutEffect(() => {
    if (alerts.length > 0) {
      const latestAlert = alerts[0];
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setVisible(latestAlert.id);

      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        setVisible(null);
      }, 5000);

      return () => {
        if (timerRef.current) clearTimeout(timerRef.current);
      };
    }
  }, [alerts]);

  if (!visible) return null;

  const alert = alerts.find((a) => a.id === visible);
  if (!alert) return null;

  const timeStr = 'now';

  return (
    <div className="alert-notification alert-notification-active">
      <div className="alert-icon">🎯</div>
      <div className="alert-content">
        <div className="alert-title">Plate Detected: {alert.plate_string}</div>
        <div className="alert-meta">
          {alert.region} • {timeStr}
        </div>
      </div>
      <button
        className="alert-close"
        onClick={() => {
          setVisible(null);
          dismissAlert(alert.id);
        }}
        aria-label="Close alert"
      >
        ✕
      </button>
    </div>
  );
}
