import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface ToastMessage {
  id: string;
  type: ToastType;
  message: string;
  duration?: number;
}

interface ToastContextType {
  showToast: (message: string, type?: ToastType, duration?: number) => void;
  success: (message: string, duration?: number) => void;
  error: (message: string, duration?: number) => void;
  warning: (message: string, duration?: number) => void;
  info: (message: string, duration?: number) => void;
}

const ToastContext = createContext<ToastContextType | null>(null);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}

let toastIdCounter = 0;
const generateToastId = () => `toast_${Date.now()}_${++toastIdCounter}`;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const removeToast = useCallback((id: string) => {
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const showToast = useCallback((message: string, type: ToastType = 'info', duration: number = 3000) => {
    const id = generateToastId();
    const toast: ToastMessage = { id, type, message, duration };

    setToasts(prev => [...prev, toast]);
    console.log(`[Toast][${type}] ${message}`);

    if (duration > 0) {
      const timer = setTimeout(() => removeToast(id), duration);
      timersRef.current.set(id, timer);
    }

    return id;
  }, [removeToast]);

  const success = useCallback((message: string, duration?: number) => showToast(message, 'success', duration), [showToast]);
  const error = useCallback((message: string, duration?: number) => showToast(message, 'error', duration || 5000), [showToast]);
  const warning = useCallback((message: string, duration?: number) => showToast(message, 'warning', duration || 4000), [showToast]);
  const info = useCallback((message: string, duration?: number) => showToast(message, 'info', duration), [showToast]);

  useEffect(() => {
    return () => {
      timersRef.current.forEach(timer => clearTimeout(timer));
      timersRef.current.clear();
    };
  }, []);

  const getIcon = (type: ToastType) => {
    switch (type) {
      case 'success':
        return (
          <svg className="w-5 h-5 text-green-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        );
      case 'error':
        return (
          <svg className="w-5 h-5 text-red-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        );
      case 'warning':
        return (
          <svg className="w-5 h-5 text-yellow-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        );
      case 'info':
      default:
        return (
          <svg className="w-5 h-5 text-cyan-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        );
    }
  };

  const getBgClass = (type: ToastType) => {
    switch (type) {
      case 'success': return 'bg-green-500/10 border-green-500/30';
      case 'error': return 'bg-red-500/10 border-red-500/30';
      case 'warning': return 'bg-yellow-500/10 border-yellow-500/30';
      case 'info':
      default: return 'bg-cyan-500/10 border-cyan-500/30';
    }
  };

  const value: ToastContextType = { showToast, success, error, warning, info };

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`flex items-start gap-3 p-3 rounded-lg border backdrop-blur-sm shadow-lg pointer-events-auto animate-slide-in ${getBgClass(toast.type)}`}
            style={{ animation: 'slideIn 0.3s ease-out' }}
          >
            {getIcon(toast.type)}
            <p className="text-white text-sm flex-1 break-words">{toast.message}</p>
            <button
              onClick={() => removeToast(toast.id)}
              className="text-gray-400 hover:text-white transition-colors flex-shrink-0 text-lg leading-none"
              aria-label="关闭"
            >
              ×
            </button>
          </div>
        ))}
      </div>
      <style>{`
        @keyframes slideIn {
          from {
            opacity: 0;
            transform: translateX(100%);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }
      `}</style>
    </ToastContext.Provider>
  );
}
