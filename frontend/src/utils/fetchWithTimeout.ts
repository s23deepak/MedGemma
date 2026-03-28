/**
 * Fetch with timeout support using AbortController
 * @param url - URL to fetch
 * @param options - Fetch options
 * @param timeoutMs - Timeout in milliseconds (default: 30000)
 * @returns Fetch response
 */
export async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs: number = 30000
): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
    return response;
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * Get appropriate timeout for different endpoint types
 * @param endpoint - API endpoint path
 * @returns Timeout in milliseconds
 */
export function getTimeoutForEndpoint(endpoint: string): number {
  if (endpoint.includes('council/deliberate')) return 60000; // 60s for deliberation
  if (endpoint.includes('transcribe')) return 120000; // 120s for ASR
  if (endpoint.includes('pubmed')) return 45000; // 45s for PubMed
  if (endpoint.includes('upload')) return 90000; // 90s for uploads
  return 30000; // 30s default
}
