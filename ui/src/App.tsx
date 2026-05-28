import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClientProvider, QueryClient } from '@tanstack/react-query';
import { LoginForm } from './components/LoginForm';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AppLayout } from './components/AppLayout';
import { AlertNotification } from './components/AlertNotification';
import { LivePage } from './pages/LivePage';
import { PlatesPage } from './pages/PlatesPage';
import { DetectionsPage } from './pages/DetectionsPage';
import { WatchlistPage } from './pages/WatchlistPage';
import { ReviewQueuePage } from './pages/ReviewQueuePage';
import { AuditLogPage } from './pages/AuditLogPage';
import { useAuth } from './hooks/useAuth';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 1000 * 60 * 5 },
  },
});

function AppRoutes() {
  useAuth();

  return (
    <Routes>
      <Route path="/login" element={<LoginForm />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<LivePage />} />
        <Route path="plates" element={<PlatesPage />} />
        <Route path="detections" element={<DetectionsPage />} />
        <Route path="watchlist" element={<WatchlistPage />} />
        <Route path="review" element={<ReviewQueuePage />} />
        <Route path="audit" element={<AuditLogPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <AppRoutes />
        <AlertNotification />
      </Router>
    </QueryClientProvider>
  );
}
