import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';

interface BackendContextType {
  backendAvailable: boolean;
  isUploading: boolean;
  isProcessing: boolean;
  setBackendAvailable: (available: boolean) => void;
  setIsUploading: (uploading: boolean) => void;
  setIsProcessing: (processing: boolean) => void;
  runBackendDiag: () => Promise<void>;
  backendDiag: {
    backend: boolean;
    python: boolean;
    ffmpeg: boolean;
    memory: boolean;
    storage: boolean;
    gpu: boolean;
    python_version?: string;
    ffmpeg_version?: string;
    gpu_info?: string;
    memory_info?: { total_gb: number; available_gb: number };
    storage_info?: { total_gb: number; available_gb: number };
  } | null;
}

const BackendContext = createContext<BackendContextType | undefined>(undefined);

export function BackendProvider({ children }: { children: ReactNode }) {
  const [backendAvailable, setBackendAvailable] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [backendDiag, setBackendDiag] = useState<BackendContextType['backendDiag']>(null);

  const checkBackendHealth = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/health', { method: 'GET' });
      setBackendAvailable(res.ok);
    } catch {
      setBackendAvailable(false);
    }
  }, []);

  const runBackendDiag = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/diag');
      if (res.ok) {
        const data = await res.json();
        setBackendDiag(data);
        setBackendAvailable(data.backend);
      } else {
        setBackendAvailable(false);
      }
    } catch {
      setBackendAvailable(false);
    }
  }, []);

  useEffect(() => {
    checkBackendHealth();
    const interval = setInterval(checkBackendHealth, 5000);
    return () => clearInterval(interval);
  }, [checkBackendHealth]);

  return (
    <BackendContext.Provider
      value={{
        backendAvailable,
        isUploading,
        isProcessing,
        setBackendAvailable,
        setIsUploading,
        setIsProcessing,
        runBackendDiag,
        backendDiag,
      }}
    >
      {children}
    </BackendContext.Provider>
  );
}

export function useBackend() {
  const context = useContext(BackendContext);
  if (context === undefined) {
    throw new Error('useBackend must be used within a BackendProvider');
  }
  return context;
}
