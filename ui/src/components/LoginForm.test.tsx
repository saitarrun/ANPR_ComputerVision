import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LoginForm } from './LoginForm';
import { useAuthStore } from '../stores/authStore';

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
    (useAuthStore as any).mockReturnValue({
      login: vi.fn(),
      isLoading: false,
      error: null,
    });

    render(<LoginForm />);
    expect(screen.getByTestId('email-input')).toBeDefined();
    expect(screen.getByTestId('password-input')).toBeDefined();
    expect(screen.getByTestId('login-button')).toBeDefined();
  });

  it('displays error message when login fails', () => {
    (useAuthStore as any).mockReturnValue({
      login: vi.fn(),
      isLoading: false,
      error: 'Invalid credentials',
    });

    render(<LoginForm />);
    expect(screen.getByText('Invalid credentials')).toBeDefined();
  });

  it('disables inputs while loading', () => {
    (useAuthStore as any).mockReturnValue({
      login: vi.fn(),
      isLoading: true,
      error: null,
    });

    render(<LoginForm />);
    const emailInput = screen.getByTestId('email-input') as HTMLInputElement;
    const passwordInput = screen.getByTestId('password-input') as HTMLInputElement;
    expect(emailInput.disabled).toBe(true);
    expect(passwordInput.disabled).toBe(true);
  });
});
