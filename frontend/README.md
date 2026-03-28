# MedGemma React Frontend

Production monitoring UI for MedGemma clinical assistant built with React 18, TypeScript, Vite, and Redux Toolkit.

## Features

- **Real-time Health Monitoring**: Service status indicators with visual feedback
- **Circuit Breaker Display**: Real-time state of 5 backend services (Firestore, LLM, PubMed, Image Analysis, ASR)
- **Responsive Design**: Works on desktop, tablet, and mobile
- **Type-Safe**: Full TypeScript for better IDE support and error catching
- **Modern Build**: Vite for fast HMR development and optimized production builds

## Quick Start

### Development

```bash
# Install dependencies
npm install

# Start development server (http://localhost:5173)
npm run dev

# Backend proxy is configured to /api → http://localhost:8000
```

### Production Build

```bash
# Build optimized production bundle
npm run build

# Output directory: ../static/dist
# Files are ready to be served by FastAPI backend
```

## Project Structure

```
src/
├── types/           # TypeScript interfaces for API responses
├── store/           # Redux slices for state management
├── hooks/           # Custom React hooks (useHealthPolling, etc.)
├── components/      # React components (Header, HealthIndicator, etc.)
├── services/        # API clients and service integrations
├── utils/           # Utility functions (backoff, fetch, formatters)
└── styles/          # Global and component styles
```

## State Management (Redux)

### Health Slice
- Tracks service health status (ready/unavailable)
- Stores circuit breaker states (CLOSED/OPEN/HALF_OPEN)
- Polled every 5 seconds from `/api/health` and `/api/status`

### Metrics Slice
- Tracks request latency, error rates, active sessions
- Polled from `/api/metrics` (dashboard only, 10s intervals)

### Rate Limit Slice
- Tracks per-endpoint request timestamps
- Tracks rate limit windows
- Prevents exceeding per-role quotas

## Hooks

### useHealthPolling()
Auto-starts on app mount, polls health/status every 5s:
```typescript
export default function MyComponent() {
  const health = useHealthPolling(); // Returns after first poll
  // Health state available via Redux useSelector
}
```

### useFetchWithRetry() (Coming in Phase 3)
Automatic retry with exponential backoff and circuit breaker awareness:
```typescript
const { data, loading, error } = useFetchWithRetry('/api/endpoint', {
  method: 'POST',
  body: JSON.stringify(payload),
  retryOptions: { maxRetries: 3 }
});
```

## API Integration

All API calls proxy through Vite dev server to `http://localhost:8000/api`:

```
Client Request:  POST /api/council/deliberate
                 ↓
Vite Proxy:      http://localhost:8000/api/council/deliberate
                 ↓
Response:        JSON back to client
```

## Configuration

### Vite Config (`vite.config.ts`)
- Dev port: 5173
- Build output: `../static/dist`
- API proxy: `http://localhost:8000`
- Code splitting: vendor, redux, charts

### TypeScript Config (`tsconfig.json`)
- Target: ES2020
- Module: ESNext
- Path alias: `@/*` → `src/*`
- Strict mode enabled

## Development Workflow

1. **Local Development**:
   ```bash
   npm run dev
   # Open http://localhost:5173
   ```

2. **Testing Changes**:
   - Edit React components
   - Vite provides HMR (hot module replacement)
   - Observe health indicators for real-time feedback

3. **Production Build**:
   ```bash
   npm run build
   # Next time backend starts, new UI is served
   ```

4. **Backend Integration**:
   - Backend serves built bundle from `static/dist/index.html`
   - API calls still go to Python backend

## Dependencies

- **react** (18.2.0) - UI framework
- **react-dom** (18.2.0) - DOM rendering
- **react-router-dom** (6.20.0) - Routing
- **@reduxjs/toolkit** (1.9.7) - State management
- **react-redux** (8.1.3) - React-Redux bindings
- **recharts** (2.10.3) - Charts for metrics dashboard
- **axios** (1.6.2) - HTTP client
- **typescript** - Type checking
- **vite** - Build tool

## Architecture Phases

### Phase 1: Foundation ✓
- React setup with TypeScript + Vite
- Redux store configuration
- Health polling hook
- Header with health/CB indicators
- Utility functions and types

### Phase 2: Monitoring (Next)
- Rate limit error handling (429 responses)
- Automatic retry with exponential backoff
- Circuit breaker aware retries
- Rate limit tracking per endpoint

### Phase 3: Dashboard (Optional)
- Real-time metrics display
- Circuit breaker grid with details
- Request latency charts
- Error rate tracking

## Troubleshooting

### Port Already in Use
```bash
# Use different port
npm run dev -- --port 5174
```

### API Proxy Not Working
- Ensure Python backend runs on `http://localhost:8000`
- Check `/api/health` endpoint responds to frontend requests
- Verify CORS headers if needed

### Build Errors
```bash
# Clear cache and rebuild
rm -rf dist node_modules
npm install
npm run build
```

## Contributing

1. Keep components small and focused
2. Use hooks for state management (Redux or custom hooks)
3. Add TypeScript types for all props and functions
4. Follow existing CSS naming conventions
5. Test components in both dev and production builds

## License

Part of MedGemma Clinical Assistant Platform
