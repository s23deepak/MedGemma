/**
 * Calculate exponential backoff delay
 * @param attempt - Attempt number (0-based)
 * @param baseDelay - Base delay in milliseconds
 * @param maxDelay - Maximum delay in milliseconds
 * @returns Delay in milliseconds
 */
export function calculateBackoff(
  attempt: number,
  baseDelay: number = 1000,
  maxDelay: number = 300000
): number {
  const delay = baseDelay * Math.pow(2, attempt);
  return Math.min(delay, maxDelay);
}

/**
 * Get backoff delay for rate limit (429) errors
 * @param attempt - Attempt number (0-based)
 * @returns Delay in milliseconds
 */
export function getRateLimitBackoff(attempt: number): number {
  // Rate limit backoff: 30s, 60s, 120s
  const baseDelay = 30000; // 30 seconds
  return calculateBackoff(attempt, baseDelay, 300000);
}

/**
 * Get backoff delay for service recovery (5xx with circuit breaker)
 * @param attempt - Attempt number (0-based)
 * @returns Delay in milliseconds
 */
export function getServiceRecoveryBackoff(attempt: number): number {
  // Service recovery: 1s, 2s, 4s, 8s, 16s
  const baseDelay = 1000; // 1 second
  return calculateBackoff(attempt, baseDelay, 60000);
}

/**
 * Format milliseconds to human-readable time string
 * @param ms - Milliseconds
 * @returns Formatted string (e.g., "2m 30s")
 */
export function formatBackoffTime(ms: number): string {
  if (ms < 1000) return `${Math.ceil(ms / 1000)}s`;

  const totalSeconds = Math.ceil(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (minutes === 0) return `${seconds}s`;
  if (seconds === 0) return `${minutes}m`;
  return `${minutes}m ${seconds}s`;
}
