import React, { createContext, useContext, useState, useCallback, useEffect, useRef, ReactNode } from 'react';

interface BackendContextType {
  backendAvailable: boolean;
  hasUpstreamActivity: boolean;
  hasDownstreamActivity: boolean;
  setBackendAvailable: (available: boolean) => void;
  triggerUpstream: () => void;
  triggerDownstream: () => void;
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

// 活动指示持续时间（毫秒）
const ACTIVITY_DURATION = 500;

export function BackendProvider({ children }: { children: ReactNode }) {
  const [backendAvailable, setBackendAvailable] = useState(false);
  const [hasUpstreamActivity, setHasUpstreamActivity] = useState(false);
  const [hasDownstreamActivity, setHasDownstreamActivity] = useState(false);
  const [backendDiag, setBackendDiag] = useState<BackendContextType['backendDiag']>(null);

  const upstreamTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const downstreamTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const triggerUpstream = useCallback(() => {
    setHasUpstreamActivity(true);
    if (upstreamTimeoutRef.current) {
      clearTimeout(upstreamTimeoutRef.current);
    }
    upstreamTimeoutRef.current = setTimeout(() => {
      setHasUpstreamActivity(false);
    }, ACTIVITY_DURATION);
  }, []);

  const triggerDownstream = useCallback(() => {
    setHasDownstreamActivity(true);
    if (downstreamTimeoutRef.current) {
      clearTimeout(downstreamTimeoutRef.current);
    }
    downstreamTimeoutRef.current = setTimeout(() => {
      setHasDownstreamActivity(false);
    }, ACTIVITY_DURATION);
  }, []);

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

  useEffect(() => {
    return () => {
      if (upstreamTimeoutRef.current) clearTimeout(upstreamTimeoutRef.current);
      if (downstreamTimeoutRef.current) clearTimeout(downstreamTimeoutRef.current);
    };
  }, []);

  return (
    <BackendContext.Provider
      value={{
        backendAvailable,
        hasUpstreamActivity,
        hasDownstreamActivity,
        setBackendAvailable,
        triggerUpstream,
        triggerDownstream,
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
