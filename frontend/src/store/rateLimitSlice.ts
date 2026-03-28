import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface RateLimitState {
  requestTimestamps: Record<string, number[]>; // endpoint -> [timestamps in ms]
  limitedUntil: Record<string, number | null>; // endpoint -> unix timestamp or null
  perRequestInProgress: Record<string, boolean>; // endpoint -> is request in progress
}

const initialState: RateLimitState = {
  requestTimestamps: {},
  limitedUntil: {},
  perRequestInProgress: {},
};

const rateLimitSlice = createSlice({
  name: 'rateLimit',
  initialState,
  reducers: {
    recordRequest: (state, action: PayloadAction<string>) => {
      const endpoint = action.payload;
      const now = Date.now();
      if (!state.requestTimestamps[endpoint]) {
        state.requestTimestamps[endpoint] = [];
      }
      state.requestTimestamps[endpoint].push(now);
      // Keep only last 60 seconds of timestamps
      const oneMinuteAgo = now - 60000;
      state.requestTimestamps[endpoint] = state.requestTimestamps[endpoint].filter(
        (ts) => ts > oneMinuteAgo
      );
    },
    setRateLimited: (state, action: PayloadAction<{ endpoint: string; until: number }>) => {
      state.limitedUntil[action.payload.endpoint] = action.payload.until;
    },
    clearRateLimited: (state, action: PayloadAction<string>) => {
      state.limitedUntil[action.payload] = null;
    },
    setRequestInProgress: (state, action: PayloadAction<{ endpoint: string; inProgress: boolean }>) => {
      state.perRequestInProgress[action.payload.endpoint] = action.payload.inProgress;
    },
  },
});

export const {
  recordRequest,
  setRateLimited,
  clearRateLimited,
  setRequestInProgress,
} = rateLimitSlice.actions;
export default rateLimitSlice.reducer;
