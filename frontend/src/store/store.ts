import { configureStore } from '@reduxjs/toolkit';
import healthReducer from './healthSlice';
import metricsReducer from './metricsSlice';
import rateLimitReducer from './rateLimitSlice';

export const store = configureStore({
  reducer: {
    health: healthReducer,
    metrics: metricsReducer,
    rateLimit: rateLimitReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

export default store;
