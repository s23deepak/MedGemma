/**
 * Format milliseconds to a readable latency string
 * @param ms - Milliseconds
 * @returns Formatted string (e.g., "250ms", "1.5s")
 */
export function formatLatency(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/**
 * Format percentage to string
 * @param percent - Percentage (0-100)
 * @param decimals - Number of decimal places (default: 1)
 * @returns Formatted string (e.g., "12.5%")
 */
export function formatPercent(percent: number, decimals: number = 1): string {
  return `${percent.toFixed(decimals)}%`;
}

/**
 * Format number with thousands separator
 * @param num - Number to format
 * @returns Formatted string (e.g., "1,234")
 */
export function formatNumber(num: number): string {
  return num.toLocaleString();
}

/**
 * Format service name for display
 * @param serviceName - Service name (e.g., "firestore", "llm_inference")
 * @returns Formatted display name (e.g., "Firestore", "LLM Inference")
 */
export function formatServiceName(serviceName: string): string {
  return serviceName
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/**
 * Get color for circuit breaker state
 * @param state - Circuit breaker state
 * @returns CSS color class name
 */
export function getCircuitBreakerColor(state: 'CLOSED' | 'OPEN' | 'HALF_OPEN'): string {
  switch (state) {
    case 'CLOSED':
      return 'text-green-600 bg-green-50';
    case 'HALF_OPEN':
      return 'text-yellow-600 bg-yellow-50';
    case 'OPEN':
      return 'text-red-600 bg-red-50';
    default:
      return 'text-gray-600 bg-gray-50';
  }
}
