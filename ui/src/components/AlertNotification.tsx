import { useEffect, useState } from 'react';
import { useAlertStore } from '../stores/alertStore';
import '../styles/AlertNotification.css';

export function AlertNotification() {
  const { alerts, dismissAlert } = useAlertStore();
  const [visible, setVisible] = useState<string | null>(null);

  useEffect(() => {
    if (alerts.length > 0) {
      const latestAlert = alerts[0];
      setVisible(latestAlert.id);

      const timer = setTimeout(() => {
        setVisible(null);
      }, 5000);

      return () => clearTimeout(timer);
    }
  }, [alerts]);

  if (!visible) return null;

  const alert = alerts.find((a) => a.id === visible);
  if (!alert) return null;

  const timeAgo = Math.round((Date.now() - alert.timestamp) / 1000);
  const timeStr = timeAgo < 60 ? `${timeAgo}s ago` : `${Math.round(timeAgo / 60)}m ago`;

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
