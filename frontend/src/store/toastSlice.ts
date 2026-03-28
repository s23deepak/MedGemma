import { createSlice, PayloadAction } from '@reduxjs/toolkit'

export interface ToastMessage {
  id: string
  message: string
  type: 'success' | 'error' | 'warning' | 'info'
  duration?: number | null
}

interface ToastState {
  messages: ToastMessage[]
}

const initialState: ToastState = {
  messages: [],
}

let messageCounter = 0

const toastSlice = createSlice({
  name: 'toast',
  initialState,
  reducers: {
    addToast: (
      state,
      action: PayloadAction<{
        message: string
        type: 'success' | 'error' | 'warning' | 'info'
        duration?: number | null
      }>
    ) => {
      const id = `toast-${++messageCounter}`
      state.messages.push({
        id,
        message: action.payload.message,
        type: action.payload.type,
        duration: action.payload.duration !== undefined ? action.payload.duration : 3000,
      })
    },
    removeToast: (state, action: PayloadAction<string>) => {
      state.messages = state.messages.filter((m) => m.id !== action.payload)
    },
    clearToasts: (state) => {
      state.messages = []
    },
  },
})

export const { addToast, removeToast, clearToasts } = toastSlice.actions
export default toastSlice.reducer
