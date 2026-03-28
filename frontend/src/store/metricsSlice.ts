import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface MetricsState {
  requestsPerSecond: number;
  avgLatencyMs: number;
  errorRatePercent: number;
  activeSessionsCount: number;
  totalRequests: number;
  lastUpdate: number | null;
  loading: boolean;
  error: string | null;
}

const initialState: MetricsState = {
  requestsPerSecond: 0,
  avgLatencyMs: 0,
  errorRatePercent: 0,
  activeSessionsCount: 0,
  totalRequests: 0,
  lastUpdate: null,
  loading: false,
  error: null,
};

const metricsSlice = createSlice({
  name: 'metrics',
  initialState,
  reducers: {
    setMetricsLoading: (state, action: PayloadAction<boolean>) => {
      state.loading = action.payload;
    },
    setMetricsUpdate: (state, action: PayloadAction<Partial<MetricsState>>) => {
      Object.assign(state, action.payload);
      state.lastUpdate = Date.now();
      state.error = null;
    },
    setMetricsError: (state, action: PayloadAction<string>) => {
      state.error = action.payload;
    },
  },
});

export const { setMetricsLoading, setMetricsUpdate, setMetricsError } = metricsSlice.actions;
export default metricsSlice.reducer;
