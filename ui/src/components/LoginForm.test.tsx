import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LoginForm } from './LoginForm';
import { useAuthStore } from '../stores/authStore';

interface MockAuthStore {
  login: ReturnType<typeof vi.fn>;
  isLoading: boolean;
  error: string | null;
}

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));

vi.mock('../stores/authStore', () => ({
  useAuthStore: vi.fn(),
}));

describe('LoginForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders login form with email and password inputs', () => {
    (useAuthStore as unknown as typeof useAuthStore).mockReturnValue({
      login: vi.fn(),
      isLoading: false,
      error: null,
    } satisfies MockAuthStore);

    render(<LoginForm />);
    expect(screen.getByTestId('email-input')).toBeDefined();
    expect(screen.getByTestId('password-input')).toBeDefined();
    expect(screen.getByTestId('login-button')).toBeDefined();
  });

  it('displays error message when login fails', () => {
    (useAuthStore as unknown as typeof useAuthStore).mockReturnValue({
      login: vi.fn(),
      isLoading: false,
      error: 'Invalid credentials',
    } satisfies MockAuthStore);

    render(<LoginForm />);
    expect(screen.getByText('Invalid credentials')).toBeDefined();
  });

  it('disables inputs while loading', () => {
    (useAuthStore as unknown as typeof useAuthStore).mockReturnValue({
      login: vi.fn(),
      isLoading: true,
      error: null,
    } satisfies MockAuthStore);

    render(<LoginForm />);
    const emailInput = screen.getByTestId('email-input') as HTMLInputElement;
    const passwordInput = screen.getByTestId('password-input') as HTMLInputElement;
    expect(emailInput.disabled).toBe(true);
    expect(passwordInput.disabled).toBe(true);
  });
});
