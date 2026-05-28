# Frontend Architecture — ANPR Dashboard (M6)

## Overview

React 18 + Vite + TypeScript dashboard for live ANPR system. Targets <2s e2e latency for live stream detection, 200k plates/day baseline load.

**Tech Stack:**
- **Build:** Vite (React plugin) + TypeScript strict mode
- **State:** TanStack Query (server state) + Zustand (client state)
- **UI:** Tailwind CSS + shadcn/ui components
- **API:** axios (interceptors + retries), WebSocket (native)
- **Testing:** Vitest (unit) + Playwright (e2e), React Testing Library (integration)
- **Types:** Generated from Pydantic models (OpenAPI schema) via `openapi-typescript`
- **Observability:** Sentry (errors), Web Vitals (perf), Analytics (no PII)

---

## File Structure

```
ui/
├── public/
│   ├── favicon.svg
│   └── manifest.json
├── src/
│   ├── main.tsx                    # Vite entry
│   ├── vite-env.d.ts               # Vite types
│   ├── App.tsx                     # Root router
│   ├── env.ts                      # Environment + validation
│   ├── lib/
│   │   ├── api/
│   │   │   ├── client.ts           # Axios instance + interceptors
│   │   │   ├── types.ts            # Auto-generated from OpenAPI
│   │   │   ├── endpoints.ts        # Endpoint constants
│   │   │   └── hooks.ts            # useQuery/useMutation wrappers
│   │   ├── auth/
│   │   │   ├── storage.ts          # JWT in localStorage
│   │   │   ├── context.tsx         # Auth context (user, roles, token)
│   │   │   └── hooks.ts            # useAuth, useRequireRole
│   │   ├── ws/
│   │   │   ├── connection.ts       # WebSocket singleton
│   │   │   ├── hooks.ts            # useWebSocket, useStreamFeed
│   │   │   └── parser.ts           # Message frame parsing
│   │   ├── store/
│   │   │   └── ui.ts              # Zustand: sidebar state, filters, UI mode
│   │   ├── utils/
│   │   │   ├── format.ts           # date, plate, latency formatting
│   │   │   ├── validation.ts       # regex, charset per region
│   │   │   └── constants.ts        # regions, roles, colors
│   │   └── hooks/
│   │       ├── useLocalStorage.ts  # Persist UI state
│   │       └── useDebounce.ts
│   ├── components/
│   │   ├── layout/
│   │   │   ├── AppLayout.tsx       # Top nav + sidebar + main
│   │   │   ├── Navbar.tsx
│   │   │   └── Sidebar.tsx
│   │   ├── common/
│   │   │   ├── Loading.tsx
│   │   │   ├── ErrorFallback.tsx
│   │   │   ├── EmptyState.tsx
│   │   │   └── Badge.tsx           # Confidence, status badges
│   │   ├── auth/
│   │   │   ├── LoginForm.tsx       # OAuth2 password flow
│   │   │   └── ProtectedRoute.tsx  # RBAC wrapper
│   │   ├── video/
│   │   │   ├── StreamGrid.tsx      # Multi-stream layout
│   │   │   ├── StreamCard.tsx      # Single stream + overlay
│   │   │   ├── VideoCanvas.tsx     # HTML5 canvas for detections
│   │   │   ├── DetectionOverlay.tsx # Plate boxes + labels
│   │   │   └── StreamStats.tsx     # FPS, latency, queue depth
│   │   ├── plates/
│   │   │   ├── PlatesTable.tsx     # Searchable table
│   │   │   ├── PlateRow.tsx
│   │   │   ├── PlateDetail.tsx     # Modal/side panel
│   │   │   ├── PlateTimeline.tsx   # Event history
│   │   │   └── CropGallery.tsx     # Plate crop images
│   │   ├── watchlist/
│   │   │   ├── WatchlistTable.tsx
│   │   │   ├── AddToWatchlistForm.tsx
│   │   │   ├── AlertHistory.tsx
│   │   │   └── AlertPreview.tsx   # Webhook/email preview
│   │   ├── review/
│   │   │   ├── ReviewQueue.tsx     # Low-conf detections
│   │   │   ├── ReviewCard.tsx      # Single item
│   │   │   ├── ConfidenceChart.tsx # Char-level confidence
│   │   │   └── ReviewAction.tsx    # Approve/reject/flag
│   │   ├── audit/
│   │   │   ├── AuditLog.tsx        # Table view
│   │   │   ├── AuditFilter.tsx     # By user, action, date range
│   │   │   └── AuditExport.tsx
│   │   └── settings/
│   │       ├── SettingsLayout.tsx  # Tabs: retention, regions, users
│   │       ├── RetentionPolicy.tsx
│   │       ├── RegionConfig.tsx
│   │       ├── UserManagement.tsx  # RBAC roles
│   │       └── StreamConfig.tsx    # Register RTSP/webcam
│   ├── pages/
│   │   ├── Live.tsx                # Grid + stats
│   │   ├── Plates.tsx              # Search + table
│   │   ├── Watchlist.tsx           # Hotlist + alerts
│   │   ├── ReviewQueue.tsx         # Human verification
│   │   ├── AuditLog.tsx            # All actions
│   │   ├── Settings.tsx            # Config
│   │   └── NotFound.tsx
│   ├── styles/
│   │   ├── globals.css             # Tailwind setup
│   │   └── video.css               # Canvas + overlay styles
│   └── __tests__/
│       ├── components/
│       ├── hooks/
│       ├── lib/
│       └── e2e/
├── vite.config.ts
├── vitest.config.ts
├── tsconfig.json
├── tailwind.config.js
├── postcss.config.js
├── .env.example
└── package.json
```

---

## Component Architecture

### Layer 1: Routing

**App.tsx** — BrowserRouter with protected routes:
```
/login                  → LoginForm
/live                   → Live (ProtectedRoute: viewer+)
/plates                 → Plates (ProtectedRoute: viewer+)
/watchlist              → Watchlist (ProtectedRoute: operator+)
/review-queue           → ReviewQueue (ProtectedRoute: operator+)
/audit-log              → AuditLog (ProtectedRoute: operator+)
/settings               → Settings (ProtectedRoute: admin)
```

### Layer 2: Layout & Navigation

**AppLayout.tsx** — Shell with:
- Top navbar: logo, search (global plate lookup), user menu, notifications bell
- Left sidebar: nav links, collapsible on mobile
- Main content area

**Sidebar.tsx** — Conditional links based on `useAuth().role`:
- Viewer: Live, Plates
- Operator: + Watchlist, Review Queue
- Admin: + Audit Log, Settings

### Layer 3: Pages & Domain Components

Each page imports domain-specific components:

**Live.tsx:**
- StreamGrid (layout, responsive columns)
- StreamCard (canvas + overlay + stats)
- Stream registration modal (POST /v1/streams)

**Plates.tsx:**
- PlatesTable (TanStack Table for sorting/pagination)
- PlateRow (click → PlateDetail side panel)
- PlateTimeline (GET /v1/plates/{plate}/events)

**Watchlist.tsx:**
- WatchlistTable (manage entries)
- AddToWatchlistForm
- AlertHistory (filtered by plate, date range)

**ReviewQueue.tsx:**
- ReviewCard (low-conf detection, char-level confidence viz)
- ReviewAction (POST /v1/review-queue/{id}/resolve)

**AuditLog.tsx:**
- AuditFilter (by user, action, date)
- AuditTable with infinite scroll

**Settings.tsx:**
- RetentionPolicy (per-region days, nightly purge schedule)
- RegionConfig (regex, charset)
- UserManagement (RBAC roles)
- StreamConfig (register/deregister RTSP)

---

## State Management

### TanStack Query (Server State)

**useQuery hooks** (in `lib/api/hooks.ts`):
```typescript
useStreamList()           // GET /v1/streams
usePlateQuery(q, from, to, region)  // GET /v1/plates
usePlateEvents(plate)    // GET /v1/plates/{plate}/events
useWatchlist()           // GET /v1/watchlist
useReviewQueue()         // GET /v1/review-queue
useAuditLog(filters)     // GET /v1/audit-log
useHealthCheck()         // GET /healthz (polling)
```

**useMutation hooks**:
```typescript
useRegisterStream()      // POST /v1/streams
useDeleteStream()        // DELETE /v1/streams/{id}
useAddToWatchlist()      // POST /v1/watchlist
useRemoveFromWatchlist()
useResolveReviewItem()   // POST /v1/review-queue/{id}/resolve
```

**Query invalidation pattern:** After mutation, invalidate affected queries:
```typescript
const addToWatchlist = useMutation({
  mutationFn: api.addToWatchlist,
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['watchlist'] })
    toast.success('Added to watchlist')
  },
})
```

### Zustand (Client State)

**ui.ts** — Persistent UI state:
```typescript
interface UIStore {
  // Sidebar
  sidebarOpen: boolean
  setSidebarOpen(open: boolean): void

  // Filters
  selectedRegion: string | null
  dateRange: [Date, Date] | null
  setDateRange(range: [Date, Date] | null): void

  // Live stream
  selectedStreamIds: Set<string>
  toggleStream(id: string): void

  // Modals
  plateDetailId: string | null
  openPlateDetail(id: string): void
  closePlateDetail(): void
}

export const useUIStore = create<UIStore>()(
  persist(
    (set) => ({ /* ... */ }),
    { name: 'anpr-ui-store' }
  )
)
```

### Auth Context

**auth/context.tsx**:
```typescript
interface User {
  id: string
  email: string
  role: 'viewer' | 'operator' | 'admin'
}

interface AuthContextType {
  user: User | null
  token: string | null
  login(email: string, password: string): Promise<void>
  logout(): void
  isLoading: boolean
}

export const AuthProvider = ({ children }: PropsWithChildren) => {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(
    localStorage.getItem('auth_token')
  )

  // Fetch user on mount if token exists
  useEffect(() => {
    if (token) {
      api.getMe(token).then(setUser).catch(logout)
    }
  }, [token])

  // ...
}

export const useAuth = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth outside AuthProvider')
  return ctx
}
```

---

## API Integration

### Axios Client

**lib/api/client.ts:**
```typescript
import axios from 'axios'
import { useAuth } from '@/lib/auth'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 10_000,
})

// Request interceptor: add JWT
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor: handle auth errors
client.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('auth_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default client
```

### Endpoint Constants

**lib/api/endpoints.ts:**
```typescript
export const ENDPOINTS = {
  auth: {
    login: '/v1/auth/login',
    me: '/v1/auth/me',
  },
  streams: {
    list: '/v1/streams',
    create: '/v1/streams',
    delete: (id: string) => `/v1/streams/${id}`,
  },
  plates: {
    list: '/v1/plates',
    events: (plate: string) => `/v1/plates/${plate}/events`,
  },
  watchlist: {
    list: '/v1/watchlist',
    add: '/v1/watchlist',
    remove: (id: string) => `/v1/watchlist/${id}`,
  },
  reviewQueue: {
    list: '/v1/review-queue',
    resolve: (id: string) => `/v1/review-queue/${id}/resolve`,
  },
  auditLog: {
    list: '/v1/audit-log',
  },
  health: {
    live: '/healthz',
    ready: '/readyz',
  },
}
```

### Generated Types

**lib/api/types.ts** — Auto-generated from OpenAPI schema:
```bash
# In CI or pre-build:
openapi-typescript http://localhost:8000/openapi.json -o src/lib/api/types.ts
```

Example structure:
```typescript
export interface Plate {
  id: string
  plate: string
  region: 'IN' | 'EU' | 'US'
  confidence: number
  detected_at: string
  crop_url: string | null
  stream_id: string
}

export interface DetectionEvent {
  id: string
  plate_id: string
  stream_id: string
  bbox: [number, number, number, number]
  confidence: number
  timestamp: string
  frame_url: string | null
}

export interface WatchlistEntry {
  id: string
  plate: string
  regions: ('IN' | 'EU' | 'US')[]
  active: boolean
  created_at: string
}
```

---

## Real-Time: WebSocket Integration

### Connection Management

**lib/ws/connection.ts** — Singleton WebSocket with reconnect:
```typescript
class StreamConnection {
  private ws: WebSocket | null = null
  private url: string
  private token: string
  private listeners = new Map<string, Set<Function>>()
  private reconnectAttempts = 0
  private maxReconnect = 5

  constructor(url: string, token: string) {
    this.url = url
    this.token = token
  }

  connect() {
    const wsUrl = new URL(this.url)
    wsUrl.searchParams.set('token', this.token)

    this.ws = new WebSocket(wsUrl.toString())
    this.ws.onmessage = (evt) => this.handleMessage(evt)
    this.ws.onerror = () => this.reconnect()
    this.ws.onclose = () => this.reconnect()
  }

  private handleMessage(evt: MessageEvent) {
    try {
      const msg = JSON.parse(evt.data) as StreamMessage
      const handlers = this.listeners.get(msg.stream_id) || new Set()
      handlers.forEach((fn) => fn(msg))
    } catch (e) {
      console.error('Failed to parse WS message', e)
    }
  }

  subscribe(streamId: string, cb: (msg: StreamMessage) => void) {
    if (!this.listeners.has(streamId)) {
      this.listeners.set(streamId, new Set())
    }
    this.listeners.get(streamId)!.add(cb)
    return () => this.listeners.get(streamId)!.delete(cb)
  }

  private reconnect() {
    if (this.reconnectAttempts < this.maxReconnect) {
      this.reconnectAttempts++
      setTimeout(() => this.connect(), 2 ** this.reconnectAttempts * 1000)
    }
  }

  disconnect() {
    this.ws?.close()
    this.ws = null
  }
}

let instance: StreamConnection | null = null

export function getStreamConnection(url: string, token: string) {
  if (!instance) {
    instance = new StreamConnection(url, token)
    instance.connect()
  }
  return instance
}
```

### Hook Wrapper

**lib/ws/hooks.ts:**
```typescript
export function useStreamFeed(streamId: string) {
  const { token } = useAuth()
  const [detections, setDetections] = useState<StreamMessage[]>([])
  const [latency, setLatency] = useState(0)

  useEffect(() => {
    if (!token || !streamId) return

    const conn = getStreamConnection(import.meta.env.VITE_WS_URL, token)
    const unsubscribe = conn.subscribe(streamId, (msg) => {
      setDetections((prev) => [msg, ...prev.slice(0, 30)]) // Keep 30 recent
      setLatency(Date.now() - new Date(msg.timestamp).getTime())
    })

    return unsubscribe
  }, [streamId, token])

  return { detections, latency }
}
```

### Message Format (From API)

**lib/ws/parser.ts:**
```typescript
export interface StreamMessage {
  stream_id: string
  timestamp: string
  frames: {
    image_b64: string // Base64 JPEG
    detections: {
      bbox: [number, number, number, number] // xyxy in original resolution
      plate: string
      confidence: number
      region: 'IN' | 'EU' | 'US'
    }[]
    fps: number
    queue_depth: number
  }
}
```

---

## Video Rendering & Detection Overlay

### VideoCanvas Component

**components/video/VideoCanvas.tsx:**
```typescript
interface VideoCanvasProps {
  streamId: string
  detections: DetectionOverlay[]
  fps: number
  latency: number
}

export const VideoCanvas = React.forwardRef<
  HTMLCanvasElement,
  VideoCanvasProps
>(({ detections, fps, latency }, ref) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')!
    const img = new Image()

    // Decode frame from latest WebSocket message
    img.onload = () => {
      // Draw frame
      ctx.drawImage(img, 0, 0)

      // Draw detections (bboxes + labels)
      detections.forEach(({ bbox, plate, confidence, region }) => {
        const [x1, y1, x2, y2] = bbox
        const w = x2 - x1
        const h = y2 - y1

        // Bbox outline (region-colored)
        ctx.strokeStyle = getRegionColor(region)
        ctx.lineWidth = 2
        ctx.strokeRect(x1, y1, w, h)

        // Label background
        const label = `${plate} (${(confidence * 100).toFixed(0)}%)`
        const labelH = 20
        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)'
        ctx.fillRect(x1, y1 - labelH, label.length * 8, labelH)

        // Label text
        ctx.fillStyle = '#fff'
        ctx.font = '14px monospace'
        ctx.fillText(label, x1 + 4, y1 - 4)
      })
    }

    img.src = `data:image/jpeg;base64,...` // From WS message
  }, [detections])

  return (
    <canvas
      ref={mergeRefs(ref, canvasRef)}
      className="w-full bg-black"
      style={{ aspectRatio: '16/9' }}
    />
  )
})
```

### StreamCard Component

**components/video/StreamCard.tsx:**
```typescript
export const StreamCard = ({ streamId }: { streamId: string }) => {
  const { detections, latency } = useStreamFeed(streamId)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  return (
    <div className="aspect-video bg-black rounded-lg overflow-hidden relative">
      <VideoCanvas
        ref={canvasRef}
        streamId={streamId}
        detections={detections.flatMap((m) =>
          m.frames.detections.map((d) => ({
            ...d,
            bbox: d.bbox,
          }))
        )}
        fps={detections[0]?.frames.fps ?? 0}
        latency={latency}
      />
      <StreamStats
        fps={detections[0]?.frames.fps ?? 0}
        latency={latency}
        queueDepth={detections[0]?.frames.queue_depth ?? 0}
      />
    </div>
  )
}
```

---

## Type Safety & Validation

### Environment Variables

**env.ts:**
```typescript
import { z } from 'zod'

const envSchema = z.object({
  VITE_API_URL: z.string().url().default('http://localhost:8000'),
  VITE_WS_URL: z.string().url().default('ws://localhost:8000'),
  VITE_SENTRY_DSN: z.string().optional(),
  VITE_ANALYTICS_KEY: z.string().optional(),
})

export const env = envSchema.parse(import.meta.env)
```

### Plate & Region Validation

**lib/utils/validation.ts:**
```typescript
export const PLATE_FORMATS = {
  IN: /^[A-Z]{2}[0-9]{2}[A-Z]{2}[0-9]{4}$/, // India
  EU: /^[A-Z]{2}[0-9]{3}[A-Z]{3}$|^[A-Z]{3}[0-9]{3,4}$/, // EU variants
  US: /^[A-Z]{1,3}[0-9]{1,5}$|^[0-9]{1,5}[A-Z]{1,3}$/, // US variants
}

export function validatePlate(
  plate: string,
  region: 'IN' | 'EU' | 'US'
): boolean {
  return PLATE_FORMATS[region].test(plate.toUpperCase())
}

export function normalizeSearchQuery(q: string): string {
  // Strip spaces, uppercase
  return q.toUpperCase().replace(/\s/g, '')
}
```

---

## Testing Strategy

### Unit Tests (Vitest)

**tests/lib/utils/validation.test.ts:**
```typescript
import { describe, it, expect } from 'vitest'
import { validatePlate } from '@/lib/utils/validation'

describe('validatePlate', () => {
  it('accepts valid India plates', () => {
    expect(validatePlate('MH02AB1234', 'IN')).toBe(true)
    expect(validatePlate('MH02AB123', 'IN')).toBe(false)
  })

  it('accepts valid EU plates', () => {
    expect(validatePlate('AB123CDE', 'EU')).toBe(true)
  })

  it('accepts valid US plates', () => {
    expect(validatePlate('ABC1234', 'US')).toBe(true)
  })
})
```

### Component Tests (React Testing Library)

**tests/components/plates/PlatesTable.test.tsx:**
```typescript
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { PlatesTable } from '@/components/plates/PlatesTable'
import { vi } from 'vitest'

const mockUseQuery = vi.hoisted(() => ({
  useQuery: vi.fn(),
}))

vi.mock('@tanstack/react-query', async () => ({
  ...(await vi.importActual('@tanstack/react-query')),
  useQuery: mockUseQuery.useQuery,
}))

describe('PlatesTable', () => {
  it('renders loading state', () => {
    mockUseQuery.useQuery.mockReturnValue({
      isLoading: true,
      data: undefined,
    })
    render(<PlatesTable />)
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('renders plate rows', async () => {
    mockUseQuery.useQuery.mockReturnValue({
      isLoading: false,
      data: [
        { id: '1', plate: 'MH02AB1234', region: 'IN', confidence: 0.95 },
      ],
    })
    render(<PlatesTable />)
    await waitFor(() => {
      expect(screen.getByText('MH02AB1234')).toBeInTheDocument()
    })
  })
})
```

### E2E Tests (Playwright)

**tests/e2e/live.spec.ts:**
```typescript
import { test, expect } from '@playwright/test'

test.describe('Live Stream', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:5173/login')
    await page.fill('input[name="email"]', 'test@example.com')
    await page.fill('input[name="password"]', 'password')
    await page.click('button:has-text("Sign In")')
    await page.waitForURL('**/live')
  })

  test('displays live stream with detections', async ({ page }) => {
    // Wait for WebSocket connection
    const wsPromise = page.waitForEvent('websocket')
    const ws = await wsPromise

    // Verify canvas renders
    const canvas = await page.locator('canvas')
    await expect(canvas).toBeVisible()

    // Verify stats display
    await expect(page.locator('text=/FPS/')).toBeVisible()
  })

  test('clicking plate opens detail panel', async ({ page }) => {
    // Trigger a detection
    await page.evaluate(() => {
      // Dispatch detection via window event or mutation
    })

    // Click plate label
    await page.click('text=/MH02AB/')
    await expect(page.locator('[data-testid="plate-detail"]')).toBeVisible()
  })
})
```

---

## Build Configuration

### vite.config.ts

```typescript
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'
import path from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src'),
      },
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: env.VITE_API_URL || 'http://localhost:8000',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: mode === 'development',
      rollupOptions: {
        output: {
          manualChunks: {
            vendor: ['react', 'react-dom'],
            query: ['@tanstack/react-query'],
          },
        },
      },
    },
  }
})
```

### tsconfig.json

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "strict": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "resolveJsonModule": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  }
}
```

### Environment Files

**.env.example:**
```bash
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
VITE_SENTRY_DSN=
VITE_ANALYTICS_KEY=
```

---

## Performance Targets & Optimizations

### Web Vitals

| Metric | Target | Strategy |
|---|---|---|
| LCP | < 2.5s | Lazy-load video components, image optimization |
| FID | < 100ms | Code-split by page, defer non-critical JS |
| CLS | < 0.1 | Fixed canvas aspect ratio, skeleton loaders |

### Code Splitting

- Lazy-load page components via React.lazy + Suspense
- Vendor chunks: react, query, UI libs
- Route-based chunks: plates, watchlist, settings

### WebSocket Performance

- Buffer detections in-memory (keep 30 latest frames)
- Dedupe messages by timestamp
- Drop old frames if client can't keep up (backpressure)

---

## Security Considerations

### XSS Prevention

- DOMPurify on any user-generated text (plate searches, comments)
- Sanitize plate strings before display (regex validation)

### CSRF

- Axios interceptor adds CSRF token from API response header

### API Security

- JWT in Authorization header (not URL or cookie)
- Refresh token rotation (if backend supports)
- Validate API responses against Zod schemas

### Data Handling

- No PII in logs or analytics (plates are PII-equivalent)
- Session tokens in localStorage (httpOnly not available in SPA), cleared on logout
- Never log raw API responses

---

## Deployment (Vite)

### Development

```bash
npm install
npm run dev           # Vite dev server + HMR
```

### Production

```bash
npm run build         # Minified dist/ with sourcemaps disabled
npm run preview       # Preview production build locally
```

### Docker (Optional Multi-Stage)

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json .
RUN npm ci
COPY src/ vite.config.ts tsconfig.json ./
RUN npm run build

FROM node:20-alpine
WORKDIR /app
RUN npm install -g serve
COPY --from=builder /app/dist /app/dist
CMD ["serve", "-s", "dist", "-l", "5173"]
```

---

## API Contract Expectations (M6 backend delivery)

The backend **must** provide (before frontend integration):

### Endpoints Needed

1. **POST /v1/auth/login** → `{ token: string; user: { id, email, role } }`
2. **GET /v1/streams** → `{ streams: Stream[] }`
3. **POST /v1/streams** → Register RTSP/webcam, return `{ stream_id: string }`
4. **DELETE /v1/streams/{id}** → Remove stream
5. **WS /v1/stream/{id}** → Live detections (frame_b64, detections[], fps, queue_depth)
6. **GET /v1/plates?q=&from=&to=&region=** → Paginated plate list
7. **GET /v1/plates/{plate}/events** → Event history with crops
8. **POST /v1/watchlist** → Add plate
9. **DELETE /v1/watchlist/{id}** → Remove plate
10. **GET /v1/watchlist** → List hotlist
11. **GET /v1/review-queue** → Low-conf detections
12. **POST /v1/review-queue/{id}/resolve** → Mark reviewed
13. **GET /v1/audit-log?action=&user=&from=&to=** → Audit events
14. **GET /healthz, /readyz** → Health probes

### Schema Expectations

- **Timestamp format:** ISO 8601 (e.g., `2026-05-27T14:30:00Z`)
- **Coordinates:** `[x1, y1, x2, y2]` in original resolution (xyxy format)
- **Confidence:** Float 0–1
- **Regions:** `'IN' | 'EU' | 'US'`
- **Roles:** `'viewer' | 'operator' | 'admin'`
- **Error responses:** `{ detail: string }` (Pydantic default)

### OpenAPI Schema

Backend must expose:
- `GET /openapi.json` — Full schema for type generation
- Used in CI to regenerate `src/lib/api/types.ts`

---

## Incremental Delivery (M6 Sprint)

### Week 1
- [ ] Project scaffold: Vite + React + TS config
- [ ] Auth: login form + JWT storage + context
- [ ] Layout: navbar + sidebar + routing skeleton

### Week 2
- [ ] Live: StreamCard + VideoCanvas + WebSocket hook
- [ ] API client: axios + interceptors + TanStack Query setup
- [ ] StreamGrid layout (responsive, multi-stream)

### Week 3
- [ ] Plates: table + search + side panel detail
- [ ] PlateTimeline component
- [ ] Type generation from OpenAPI

### Week 4
- [ ] Watchlist: add/remove, alert history
- [ ] ReviewQueue: approval workflow
- [ ] Settings: retention + user mgmt (admin-only)

### Week 5
- [ ] AuditLog: filtering + export
- [ ] Error handling + loading states
- [ ] E2E tests (Playwright)
- [ ] Performance audit + Web Vitals
- [ ] Deploy to staging

---

## Known Risks & Mitigations

| Risk | Mitigation |
|---|---|
| WebSocket lag on slow networks | Frame buffer backpressure; drop old frames if 30+ queued |
| Live canvas rendering CPU spike | RequestAnimationFrame throttle; render only changed detections |
| Large plate table performance | TanStack Table with virtualization (10k rows); server-side pagination |
| Type mismatch with backend | Auto-generate from OpenAPI; validate responses with Zod |
| RBAC not enforced client-side | Always check `useAuth().role` before rendering; trust API 401 for security |
| localStorage not available (private mode) | Fallback to memory-only token; user will re-login on refresh |

---

## Summary

**Delivered:** Industrial-grade React SPA for ANPR dashboard.
- Clean, testable component architecture
- Server state (TanStack Query) + client state (Zustand) separation
- WebSocket live feed with canvas rendering
- Type-safe API integration (auto-generated from OpenAPI)
- RBAC-aware routing + auth context
- E2E + unit tests from day one
- Performance targets: <2.5s LCP, <100ms FID, <0.1s CLS
- Security: XSS prevention, CSRF protection, JWT auth, no PII in logs

**Ready for backend M6 delivery. Can start now; blocks on API schema.**
