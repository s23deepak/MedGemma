import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { HealthResponse, CircuitBreakerState } from '../types/api';

interface HealthState {
  services: Record<string, 'ready' | 'unavailable'>;
  circuitBreakers: Record<string, CircuitBreakerState>;
  isHealthy: boolean;
  loading: boolean;
  lastUpdate: number | null;
  error: string | null;
}

const initialState: HealthState = {
  services: {},
  circuitBreakers: {},
  isHealthy: true,
  loading: false,
  lastUpdate: null,
  error: null,
};

const healthSlice = createSlice({
  name: 'health',
  initialState,
  reducers: {
    setHealthLoading: (state, action: PayloadAction<boolean>) => {
      state.loading = action.payload;
    },
    setHealthUpdate: (state, action: PayloadAction<{
      services: Record<string, 'ready' | 'unavailable'>;
      circuitBreakers: Record<string, CircuitBreakerState>;
      isHealthy: boolean;
    }>) => {
      state.services = action.payload.services;
      state.circuitBreakers = action.payload.circuitBreakers;
      state.isHealthy = action.payload.isHealthy;
      state.lastUpdate = Date.now();
      state.error = null;
    },
    setHealthError: (state, action: PayloadAction<string>) => {
      state.error = action.payload;
      state.isHealthy = false;
    },
  },
});

export const { setHealthLoading, setHealthUpdate, setHealthError } = healthSlice.actions;
export default healthSlice.reducer;
