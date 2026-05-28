# ANPR Dashboard Frontend

Industrial-grade Automatic Number Plate Recognition dashboard.

## Tech Stack

- **React 18** — UI framework
- **Vite** — Build tool
- **TypeScript** — Type safety
- **Tailwind CSS** — Styling
- **TanStack Query** — Server state management
- **Zustand** — Client state management
- **React Router v6** — Navigation
- **Axios** — HTTP client
- **Radix UI** — Accessible components

## Setup

```bash
npm install
cp .env.example .env
```

## Development

```bash
npm run dev
```

Runs on http://localhost:5173 by default.

## Build

```bash
npm run build
npm run preview
```

## Project Structure

```
src/
├── components/        # Reusable UI components
├── pages/            # Page-level components
├── hooks/            # Custom React hooks
├── stores/           # Zustand state stores
├── lib/              # API client and utilities
├── App.tsx           # Main routing
└── index.css         # Global styles
```

## API Contract

### Auth Endpoints
- `POST /v1/auth/login` — Login with email/password
- `POST /v1/auth/refresh` — Refresh access token
- `GET /v1/auth/me` — Get current user

### Data Endpoints (M7 Phase 2)
- `GET /v1/regions` — List regions
- `GET /v1/cameras` — List cameras (filtered by region)
- `GET /v1/plates` — List detected plates
- `GET /v1/detections` — List frame detections

### WebSocket
- `WS /v1/stream/{stream_id}?token={jwt}` — Live detection stream

## State Management

**Client State (Zustand)**: Authentication, UI toggles
**Server State (TanStack Query)**: Regions, cameras, plates, detections

## Live <2s SLA

WebSocket endpoint provides real-time detections with <2s latency. Connected clients receive detection JSON with:
- `frame_timestamp` — frame capture time
- `plate_string` — OCR result
- `plate_confidence` — detector confidence [0–1]
- `char_confidence` — character confidence [0–1]

## Testing

Currently stubbed. Integration tests use mock API responses.

```bash
npm run test
```
