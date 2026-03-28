export interface ServiceStatus {
  status: 'ready' | 'unavailable';
}

export interface HealthResponse {
  status: string;
  timestamp: number;
  services: Record<string, ServiceStatus>;
}

export interface CircuitBreakerState {
  state: 'CLOSED' | 'OPEN' | 'HALF_OPEN';
  failure_count?: number;
  recovery_timeout?: number;
}

export interface StatusResponse {
  active_sessions: number;
  circuit_breakers: Record<string, CircuitBreakerState>;
  model_status: Record<string, { status: string }>;
  services: Record<string, boolean>;
}

export interface MetricsResponse {
  requests_total: number;
  avg_latency_ms: number;
  error_rate_percent: number;
  active_sessions: number;
  [key: string]: any;
}

export interface ApiErrorResponse {
  status_code: number;
  detail: string;
  error?: string;
}
