import { useEffect } from 'react';
import { useAuthStore } from '../stores/authStore';

export const useAuth = () => {
  const auth = useAuthStore();

  useEffect(() => {
    // Hydrate auth state on mount
    if (!auth.user && auth.isAuthenticated) {
      auth.fetchUser();
    }
  }, []);

  return auth;
};
