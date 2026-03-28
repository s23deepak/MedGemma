# Phase 3: Rate Limit Handling & Auto-Retry - Complete Implementation Guide

## Overview

Phase 3 adds production-grade error handling to the React frontend with:
- **Automatic retry logic** with exponential backoff
- **Rate limit awareness** (429 responses: 30s → 60s → 120s)
- **Circuit breaker integration** (OPEN/HALF_OPEN/CLOSED states)
- **Global toast notifications** for user feedback
- **Interactive test page** to verify retry behavior

**Status**: ✅ Ready for production use

---

## Architecture Diagram

```
User clicks button
       ↓
Component calls: useFetchWithRetry()
       ↓
Hook auto-fetches on mount
       ↓
apiClient.request() with retry options
       ↓
   Request fails?
   ├─ 429 (Rate limit) → 30s wait → Retry
   ├─ 5xx + OPEN CB → 5-60s wait → Retry
   ├─ 5xx + HALF_OPEN CB → 2-30s wait → Retry
   ├─ 5xx + CLOSED CB → 1-10s wait → Retry
   ├─ 4xx → No retry, show error
   └─ Timeout → 1-10s wait → Retry
       ↓
Show "Retrying in 45 seconds..." toast
       ↓
Countdown ends → Retry request
       ↓
Success → Update Redux → Re-render with data
Error → Show error toast → Manual refetch available
```

---

## Core Components

### 1. API Client (`src/services/api.ts`)

**The centralized HTTP layer with retry logic**:

```typescript
import { apiClient } from '@/services/api'

// Simple GET
const response = await apiClient.get('/api/health')
if (response.ok) {
  console.log('Data:', response.data)
} else {
  console.error('Error:', response.error)
}

// POST with retry
const response = await apiClient.post('/api/council/deliberate', payload, {
  timeout: 60000, // 60 second operation timeout
  retryOptions: {
    maxRetries: 3,
    baseDelay: 1000,
    onRetry: (attempt, reason, delayMs) => {
      console.log(`Attempt ${attempt}: ${reason}, waiting ${delayMs}ms`)
    }
  }
})
```

**Features**:
- 429 responses: 30s, 60s, 120s backoff
- 5xx responses: CB-aware backoff
- 4xx responses: No retry
- Timeout responses: Standard backoff
- Automatic response parsing (JSON)
- Consistent error response format

---

### 2. useFetchWithRetry Hook

**Combine with React components for automatic data fetching**:

```typescript
import { useFetchWithRetry } from '@/hooks/useFetchWithRetry'
import { useNotification } from '@/hooks/useNotification'

function MyComponent() {
  const { data, loading, error, isRetrying, retryWaitSeconds, refetch }
    = useFetchWithRetry('/api/council/cases', {
      method: 'GET',
      retryOptions: { maxRetries: 3 },
      showErrorToast: true,
      showRetryToast: true
    })

  const notify = useNotification()

  if (loading && !data) return <div>Loading...</div>
  if (isRetrying) return <div>Retrying in {retryWaitSeconds}s...</div>
  if (error) return <div>{error}</div>

  return (
    <div>
      {data && <div>{JSON.stringify(data)}</div>}
      <button onClick={refetch} disabled={loading}>
        Refresh
      </button>
      <button onClick={() => notify.info('Clicked!')} >
        Test Toast
      </button>
    </div>
  )
}
```

**Returns**:
- `data` - Response data (null until fetch completes)
- `loading` - True while fetching
- `error` - Error message if request failed
- `isRetrying` - True while waiting to retry
- `retryWaitSeconds` - Countdown timer (null if not retrying)
- `refetch()` - Manually trigger fetch again
- `reset()` - Reset state to initial

---

### 3. useNotification Hook

**Simple API for showing toasts**:

```typescript
const notify = useNotification()

notify.success('Operation successful!') // Green, 3s
notify.error('Failed to save', { duration: 5000 }) // Red, 5s
notify.warning('This action cannot be undone') // Yellow, 4s
notify.info('Processing your request...', { duration: null }) // Blue, sticky
```

**Fully Redux-backed**: toasts persist across component re-renders

---

### 4. Circuit Breaker Client (`src/services/circuitBreakerClient.ts`)

**Understands backend CB states and adjusts retry strategy**:

```typescript
import { getCurrentCircuitBreakerStatus, getMostCriticalBreakerState }
  from '@/services/circuitBreakerClient'

// In your retry handler
const cbStatus = await getCurrentCircuitBreakerStatus()
const state = getMostCriticalBreakerState(cbStatus)

switch (state) {
  case 'OPEN':
    // Service is down, wait longer
    waitTime = 5000 + attempt * 10000
    break
  case 'HALF_OPEN':
    // Service is recovering, moderate wait
    waitTime = 2000 + attempt * 5000
    break
  case 'CLOSED':
    // Service is healthy, short wait
    waitTime = 1000 * Math.pow(2, attempt)
    break
}
```

---

## Usage Examples

### Example 1: Fetch Data with Auto-Retry

```typescript
import { useFetchWithRetry } from '@/hooks/useFetchWithRetry'

function CasesPage() {
  const { data: cases, loading, error, refetch } = useFetchWithRetry(
    '/api/cases',
    { showErrorToast: true }
  )

  if (loading) return <div>Loading cases...</div>
  if (error) return <div>Error: {error}</div>

  return (
    <div>
      <h1>Cases ({cases.length})</h1>
      {cases.map(c => <div key={c.id}>{c.name}</div>)}
      <button onClick={refetch}>Refresh</button>
    </div>
  )
}
```

### Example 2: Form Submission with Retry

```typescript
import { useNotification } from '@/hooks/useNotification'
import { apiClient } from '@/services/api'

function EncounterForm() {
  const notify = useNotification()
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (data) => {
    setSubmitting(true)
    try {
      const response = await apiClient.post('/api/encounters', data, {
        timeout: 60000,
        retryOptions: { maxRetries: 3 }
      })

      if (response.ok) {
        notify.success('Encounter saved successfully')
      } else {
        notify.error(response.error || 'Failed to save')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={(e) => {
      e.preventDefault()
      handleSubmit(formData)
    }}>
      {/* Form fields */}
      <button type="submit" disabled={submitting}>
        {submitting ? 'Saving...' : 'Save'}
      </button>
    </form>
  )
}
```

### Example 3: Testing Retry Behavior

**No code needed!** Visit http://localhost:5173/api-test

This interactive page demonstrates:
- Successful retries (429 with countdown)
- Failed retries (404 without retry)
- Server errors (5xx with CB awareness)
- Total request time and retry count

---

## Retry Behavior Reference

### 429 (Too Many Requests)
```
Retry backoff: 30s → 60s → 120s
Max attempts: 3 retries
User sees: "Retrying in 30 seconds... (Attempt 1)"
           "Retrying in 60 seconds... (Attempt 2)"
           "Retrying in 120 seconds... (Attempt 3)"
After 3 failures: Show error toast
```

### 5xx (Server Error) - CLOSED Circuit Breaker
```
CB state: Service is healthy
Retry backoff: 1s → 2s → 4s (exponential)
Max attempts: 3 retries
User sees: "Connection error, retrying..." (no countdown)
After 3 failures: Show error toast
```

### 5xx (Server Error) - HALF_OPEN Circuit Breaker
```
CB state: Service is recovering
Retry backoff: 2s → 3s → 4.5s (slower, service recovering)
Max attempts: 3 retries
User sees: "Service recovering, retrying in 2 seconds..."
After 3 failures: Show error toast
```

### 5xx (Server Error) - OPEN Circuit Breaker
```
CB state: Service is down
Retry backoff: 5s → 15s → 35s (much longer wait)
Max attempts: 3 retries
User sees: "Service recovering, retrying in 5 seconds..."
After 3 failures: Show error toast with "Service unavailable"
```

### 4xx (Client Error)
```
Examples: 400, 401, 403, 404
Behavior: NO RETRY
User sees: Error toast immediately
Reason: Client error - user/request is wrong, retrying won't help
```

### Timeout
```
Default timeout: 30 seconds
Operation-specific timeouts:
  - Council deliberation: 60 seconds
  - Audio transcription (ASR): 120 seconds
  - PubMed search: 45 seconds
  - File upload: 90 seconds
Retry backoff: 1s → 2s → 4s
Max attempts: 3 retries
```

---

## Configuration

### Per-Endpoint Timeout

```typescript
// Default: 30 seconds
await apiClient.get('/api/health')

// Custom timeout: 5 seconds (for health check)
await apiClient.get('/api/health', { timeout: 5000 })

// Automatic (by endpoint):
// /api/council/deliberate → 60000ms
// /api/transcribe → 120000ms
// /api/upload → 90000ms
// others → 30000ms
```

### Toast Duration

```typescript
notify.success('Done', { duration: 2000 }) // 2 seconds
notify.error('Failed', { duration: null }) // Sticky (manual dismiss)
notify.info('Processing...', { duration: null }) // Sticky
```

### Retry Options

```typescript
const options = {
  timeout: 45000, // Overall request timeout
  retryOptions: {
    maxRetries: 3, // Number of retry attempts
    baseDelay: 1000, // Initial backoff (1 second)
    onRetry: (attempt, reason, delayMs) => {
      console.log(`Retry ${attempt} in ${delayMs}ms: ${reason}`)
    }
  }
}

await apiClient.post('/api/endpoint', data, options)
```

---

## Testing Retry Logic

### Local Testing

```bash
# Start dev server
cd frontend
npm install
npm run dev

# Open test page
http://localhost:5173/api-test

# Click buttons to test different scenarios
- Green check: Successful health check
- Yellow warning: Simulates 4xx (no retry)
- Red X: Simulates error during retry countdown
```

### Simulate Rate Limiting

In Python backend, if you want to test 429 handling:

```python
# Temporarily lower rate limits for testing
@app.get("/api/council/deliberate")
async def test_429():
    raise HTTPException(status_code=429, detail="Rate limit exceeded")
```

Then visit http://localhost:5173/api-test and observe the 30s countdown.

---

## Error Handling Best Practices

### ✅ Good: Use useNotification for user feedback
```typescript
try {
  const response = await apiClient.post('/api/data', payload)
  if (response.ok) {
    notify.success('Saved successfully')
  } else {
    notify.error(response.error)
  }
} catch (error) {
  notify.error('Network error: ' + error.message)
}
```

### ✅ Good: Let useFetchWithRetry handle retries
```typescript
const { data, error } = useFetchWithRetry('/api/data', {
  showErrorToast: true,
  showRetryToast: true
})
```

### ❌ Bad: Manual retry logic (unnecessary, error-prone)
```typescript
// Don't do this - apiClient handles it!
let attempts = 0
while (attempts < 3) {
  try {
    const res = await fetch('/api/data')
    if (res.ok) break
  } catch {
    attempts++
    if (attempts < 3) await delay(1000 * attempts)
  }
}
```

---

## Production Deployment

### Build for Production
```bash
cd frontend
npm run build
# Output: ../static/dist/
```

### Serve with Python Backend
```python
from fastapi.staticfiles import StaticFiles
import os

# In main.py, after creating FastAPI app
if os.path.exists('static/dist'):
    app.mount('/', StaticFiles(directory='static/dist', html=True), name='frontend')
```

### Environment Variables
```bash
# .env (frontend directory)
VITE_API_BASE=http://localhost:8000
VITE_API_RETRY_MAX=3
```

Usage in code:
```typescript
const apiBase = import.meta.env.VITE_API_BASE
const maxRetries = import.meta.env.VITE_API_RETRY_MAX
```

---

## Troubleshooting

### Issue: Toasts not showing
**Solution**: Ensure `<ToastContainer>` is in `App.tsx` root component

### Issue: Retry not happening
**Check**:
1. Is it a 4xx error? (These don't retry)
2. Are you using `apiClient` or `fetch()`? (Only `apiClient` retries)
3. Check browser console for error details

### Issue: Rate limit countdown wrong
**Check**: Browser console for `Retrying in...` messages from retry handler

### Issue: High latency/long waits
**Expected**: Rate limits wait 30-120s by design. Reduce requests or request increased quota.

---

## What's Next: Phase 4 (Optional)

**Monitoring Dashboard** - Real-time metrics visualization
- Request latency chart
- Error rate chart
- Active sessions gauge
- Rate limit heatmap
- Circuit breaker detailed view
- Route: `/monitoring`

When Phase 4 is done, MedGemma will have:
- ✅ Real-time health monitoring (Phase 2)
- ✅ Smart auto-retry (Phase 3)
- ✅ Metrics dashboard (Phase 4)
- ✅ Full production readiness

---

## File Reference

| File | Purpose | Lines |
|------|---------|-------|
| `src/services/api.ts` | API client with retry logic | 400+ |
| `src/services/circuitBreakerClient.ts` | CB-aware retry strategies | 200 |
| `src/hooks/useFetchWithRetry.ts` | React hook for auto-retry | 150 |
| `src/hooks/useNotification.ts` | Toast trigger API | 30 |
| `src/store/toastSlice.ts` | Redux state for toasts | 50 |
| `src/components/Toast.tsx` | Toast UI component | 50 |
| `src/components/Pages/ApiTestPage.tsx` | Interactive test page | 120 |

**Total Phase 3**: ~1000 lines of production code

---

## Summary

Phase 3 transforms the frontend from a simple UI into production-grade infrastructure with:

1. **Automatic retry** - Users don't have to manually retry failed requests
2. **Smart backoff** - Different strategies for different error types
3. **CB awareness** - Respects backend circuit breaker state
4. **User feedback** - Clear toasts explain what's happening
5. **Developer friendly** - Simple hooks and client API

Ready to move to Phase 4 (Dashboard) or deploy to production!
