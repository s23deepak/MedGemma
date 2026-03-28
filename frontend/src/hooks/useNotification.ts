import { useDispatch } from 'react-redux'
import { addToast } from '../store/toastSlice'
import { AppDispatch } from '../store/store'

interface UseNotificationOptions {
  duration?: number | null // null = sticky toast
}

export function useNotification() {
  const dispatch = useDispatch<AppDispatch>()

  return {
    success: (message: string, options?: UseNotificationOptions) => {
      dispatch(addToast({ message, type: 'success', duration: options?.duration ?? 3000 }))
    },
    error: (message: string, options?: UseNotificationOptions) => {
      dispatch(addToast({ message, type: 'error', duration: options?.duration ?? 5000 }))
    },
    warning: (message: string, options?: UseNotificationOptions) => {
      dispatch(addToast({ message, type: 'warning', duration: options?.duration ?? 4000 }))
    },
    info: (message: string, options?: UseNotificationOptions) => {
      dispatch(addToast({ message, type: 'info', duration: options?.duration ?? 3000 }))
    },
  }
}
