import { useEffect, useReducer, useCallback } from 'react'
import { useDispatch } from 'react-redux'
import { apiClient, ApiClientOptions, ApiResponse } from '../services/api'
import { addToast } from '../store/toastSlice'
import { formatBackoffTime } from '../utils/exponentialBackoff'
import { AppDispatch } from '../store/store'

interface UseFetchState<T> {
  data: T | null
  loading: boolean
  error: string | null
  isRetrying: boolean
  retryCount: number
  retryWaitSeconds: number | null
}

type UseFetchAction<T> =
  | { type: 'LOADING' }
  | { type: 'SUCCESS'; data: T }
  | { type: 'ERROR'; error: string }
  | { type: 'RETRY_START'; delay: number }
  | { type: 'RETRY_TICK' }
  | { type: 'RETRY_END' }
  | { type: 'RESET' }

function createInitialState<T>(): UseFetchState<T> {
  return {
    data: null,
    loading: false,
    error: null,
    isRetrying: false,
    retryCount: 0,
    retryWaitSeconds: null,
  }
}

function useFetchReducer<T>(state: UseFetchState<T>, action: UseFetchAction<T>): UseFetchState<T> {
  switch (action.type) {
    case 'LOADING':
      return { ...state, loading: true, error: null }
    case 'SUCCESS':
      return {
        ...state,
        data: action.data,
        loading: false,
        error: null,
        retryCount: 0,
        retryWaitSeconds: null,
      }
    case 'ERROR':
      return { ...state, loading: false, error: action.error }
    case 'RETRY_START':
      return {
        ...state,
        isRetrying: true,
        retryCount: state.retryCount + 1,
        retryWaitSeconds: Math.ceil(action.delay / 1000),
      }
    case 'RETRY_TICK':
      return {
        ...state,
        retryWaitSeconds:
          state.retryWaitSeconds === null ? null : Math.max(0, state.retryWaitSeconds - 1),
      }
    case 'RETRY_END':
      return { ...state, isRetrying: false, retryWaitSeconds: null }
    case 'RESET':
      return createInitialState<T>()
    default:
      return state
  }
}

interface UseFetchWithRetryOptions extends ApiClientOptions {
  showErrorToast?: boolean
  showRetryToast?: boolean
}

/**
 * Hook for fetching data with automatic retry, circuit breaker awareness, and rate limit handling
 * @param endpoint - API endpoint to fetch from
 * @param options - Request options (method, body, headers, retry options, etc.)
 * @returns Object with data, loading, error, isRetrying, and refetch function
 */
export function useFetchWithRetry<T = any>(
  endpoint: string,
  options: UseFetchWithRetryOptions = {}
) {
  const { showErrorToast = true, showRetryToast = true, ...apiOptions } = options
  const [state, dispatch] = useReducer(useFetchReducer, null, createInitialState<T>)
  const reduxDispatch = useDispatch<AppDispatch>()

  const performFetch = useCallback(async () => {
    dispatch({ type: 'LOADING' })

    const response = await apiClient.request<T>(endpoint, {
      ...apiOptions,
      retryOptions: {
        ...apiOptions.retryOptions,
        onRetry: (attempt, reason, delay) => {
          const delayStr = formatBackoffTime(delay)

          if (showRetryToast && attempt <= 2) {
            // Only show retry toasts for first 2 attempts
            reduxDispatch(
              addToast({
                message: `Retrying in ${delayStr}... (Attempt ${attempt})`,
                type: 'info',
                duration: null, // Sticky until retry completes
              })
            )
          }

          dispatch({ type: 'RETRY_START'; delay })

          // Countdown timer
          const countdown = setInterval(() => {
            dispatch({ type: 'RETRY_TICK' })
          }, 1000)

          setTimeout(() => {
            clearInterval(countdown)
            dispatch({ type: 'RETRY_END' })
          }, delay)
        },
      },
    })

    if (response.ok && response.data) {
      dispatch({ type: 'SUCCESS'; data: response.data })
    } else {
      const error = response.error || 'Request failed'
      dispatch({ type: 'ERROR'; error })

      if (showErrorToast) {
        reduxDispatch(
          addToast({
            message: error,
            type: 'error',
            duration: 5000,
          })
        )
      }
    }
  }, [endpoint, apiOptions, showErrorToast, showRetryToast, reduxDispatch])

  // Fetch on mount or when endpoint/options change
  useEffect(() => {
    performFetch()
  }, [performFetch])

  return {
    data: state.data,
    loading: state.loading,
    error: state.error,
    isRetrying: state.isRetrying,
    retryCount: state.retryCount,
    retryWaitSeconds: state.retryWaitSeconds,
    refetch: performFetch,
    reset: () => dispatch({ type: 'RESET' }),
  }
}

export default useFetchWithRetry
