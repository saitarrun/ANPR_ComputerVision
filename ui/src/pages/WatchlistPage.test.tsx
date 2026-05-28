import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { WatchlistPage } from './WatchlistPage';
import * as api from '../lib/api';

vi.mock('../lib/api');

const mockRegions = [
  {
    id: '1',
    code: 'IN',
    name: 'India',
    regex: '[0-9]{2}[A-Z]{2}[0-9]{4}',
    charset: '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ',
    retention_days: 30,
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
  },
];

const mockWatchlist = [
  {
    id: '1',
    plate_pattern: '[0-9]{3}[A-Z]{2}[0-9]{4}',
    region_id: '1',
    reason: 'Test watchlist',
    priority: 0,
    alert_enabled: true,
    alert_channel: 'webhook' as const,
    dedup_window: 300,
    last_hit: '2025-01-01T12:00:00Z',
    hit_count: 5,
    created_by_user_id: 'user1',
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
  },
];

describe('WatchlistPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    vi.mocked(api.regionsAPI.list).mockResolvedValue({
      data: mockRegions,
    } as any);

    vi.mocked(api.watchlistAPI.list).mockResolvedValue({
      data: mockWatchlist,
    } as any);
  });

  const renderPage = () => {
    return render(
      <QueryClientProvider client={queryClient}>
        <WatchlistPage />
      </QueryClientProvider>
    );
  };

  it('should render watchlist page with title', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Watchlist Patterns')).toBeTruthy();
    });
    expect(screen.getByText('+ Add Pattern')).toBeTruthy();
  });

  it('should display watchlist items in table', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('[0-9]{3}[A-Z]{2}[0-9]{4}')).toBeTruthy();
    });

    expect(screen.getByText('India')).toBeTruthy();
    expect(screen.getByText('webhook')).toBeTruthy();
    expect(screen.getByText('5')).toBeTruthy();
  });

  it('should show form when add button clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    const addButton = screen.getByText('+ Add Pattern');
    await user.click(addButton);

    expect(screen.getByText('Add New Pattern')).toBeTruthy();
    expect(screen.getByTestId('pattern-input')).toBeTruthy();
    expect(screen.getByTestId('region-select')).toBeTruthy();
  });

  it('should create new watchlist pattern', async () => {
    const user = userEvent.setup();

    vi.mocked(api.watchlistAPI.create).mockResolvedValueOnce({
      data: mockWatchlist[0],
    } as any);

    renderPage();

    const addButton = screen.getByText('+ Add Pattern');
    await user.click(addButton);

    const patternInput = screen.getByTestId('pattern-input');
    const regionSelect = screen.getByTestId('region-select');

    await user.type(patternInput, '[0-9]{4}[A-Z]{3}');
    await user.selectOptions(regionSelect, '1');

    const submitButton = screen.getByRole('button', { name: 'Create' });
    await user.click(submitButton);

    await waitFor(() => {
      expect(api.watchlistAPI.create).toHaveBeenCalled();
    });
  });

  it('should filter watchlist by region', async () => {
    const user = userEvent.setup();
    renderPage();

    const regionFilter = screen.getByTestId('region-filter');
    await user.selectOptions(regionFilter, '1');

    await waitFor(() => {
      expect(api.watchlistAPI.list).toHaveBeenCalled();
    });
  });

  it('should delete watchlist pattern', async () => {
    const user = userEvent.setup();

    vi.mocked(api.watchlistAPI.delete).mockResolvedValueOnce(undefined as any);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('delete-btn-1')).toBeTruthy();
    });

    const deleteButton = screen.getByTestId('delete-btn-1');
    await user.click(deleteButton);

    await waitFor(() => {
      expect(api.watchlistAPI.delete).toHaveBeenCalledWith('1');
    });
  });

  it('should show empty state when no patterns', async () => {
    vi.mocked(api.watchlistAPI.list).mockResolvedValueOnce({
      data: [],
    } as any);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('No watchlist patterns yet.')).toBeTruthy();
    });
  });
});
