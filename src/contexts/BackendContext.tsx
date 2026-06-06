import React, { createContext, useContext, useState, useCallback, useEffect, useRef, ReactNode } from 'react';

type ConnectionStatus = 'connected' | 'disconnected' | 'unstable';

interface FrontendDiag {
  user_agent: string;
  platform: string;
  language: string;
  online: boolean;
  screen: string;
  viewport: string;
  pixel_ratio: number;
  connection_type: string;
  timestamp: string;
  error_detail: string;
}

interface BackendContextType {
  backendAvailable: boolean;
  connectionStatus: ConnectionStatus;
  hasUpstreamActivity: boolean;
  hasDownstreamActivity: boolean;
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
    memory_info?: { total_gb: number; available_gb: number; used_percent?: number };
    storage_info?: { total_gb: number; available_gb: number; used_percent?: number };
    timestamp?: string;
    system?: { os: string; arch: string; platform: string; hostname: string };
    runtime?: { pid: number; mobile_mode: boolean; uptime_seconds: number | null; algorithm_versions: string[] };
    directories?: { upload_files: number; output_files: number; decoded_files: number };
    process?: { cpu_percent: number; memory_mb: number; threads: number; fd_count: number | null };
    frontend?: FrontendDiag;
  } | null;
}

const BackendContext = createContext<BackendContextType | undefined>(undefined);

const ACTIVITY_DURATION = 800;
const UNSTABLE_THRESHOLD = 2;

export function getFrontendDiag(errorDetail: string = ''): FrontendDiag {
  const nav = navigator as any;
  return {
    user_agent: navigator.userAgent,
    platform: navigator.platform,
    language: navigator.language,
    online: navigator.onLine,
    screen: `${screen.width}x${screen.height}`,
    viewport: `${window.innerWidth}x${window.innerHeight}`,
    pixel_ratio: window.devicePixelRatio,
    connection_type: nav.connection?.effectiveType || nav.connection?.type || 'unknown',
    timestamp: new Date().toISOString(),
    error_detail: errorDetail,
  };
}

function setupNetworkInterceptor(
  onRequest: () => void,
  onResponse: (success: boolean) => void
) {
  const originalFetch = window.fetch;

  window.fetch = async function(...args) {
    onRequest();
    try {
      const response = await originalFetch.apply(this, args);
      onResponse(response.ok);
      return response;
    } catch (error) {
      onResponse(false);
      throw error;
    }
  };

  return () => {
    window.fetch = originalFetch;
  };
}

export function BackendProvider({ children }: { children: ReactNode }) {
  const [backendAvailable, setBackendAvailable] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected');
  const [hasUpstreamActivity, setHasUpstreamActivity] = useState(false);
  const [hasDownstreamActivity, setHasDownstreamActivity] = useState(false);
  const [backendDiag, setBackendDiag] = useState<BackendContextType['backendDiag']>(null);

  const upstreamTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const downstreamTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const consecutiveFailuresRef = useRef(0);

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

  const handleResponseSuccess = useCallback((success: boolean) => {
    triggerDownstream();
    if (success) {
      consecutiveFailuresRef.current = 0;
      setConnectionStatus('connected');
      setBackendAvailable(true);
    } else {
      consecutiveFailuresRef.current++;
      if (consecutiveFailuresRef.current >= UNSTABLE_THRESHOLD) {
        setConnectionStatus('unstable');
        setBackendAvailable(false);
      }
    }
  }, [triggerDownstream]);

  const checkBackendHealth = useCallback(async () => {
    try {
      const res = await fetch('/health', { method: 'GET' });
      if (res.ok) {
        consecutiveFailuresRef.current = 0;
        setBackendAvailable(true);
        setConnectionStatus('connected');
      } else {
        consecutiveFailuresRef.current++;
        if (consecutiveFailuresRef.current >= UNSTABLE_THRESHOLD) {
          setConnectionStatus('unstable');
          setBackendAvailable(false);
        }
      }
    } catch {
      consecutiveFailuresRef.current++;
      if (consecutiveFailuresRef.current >= UNSTABLE_THRESHOLD) {
        setConnectionStatus('disconnected');
        setBackendAvailable(false);
      }
    }
  }, []);

  const runBackendDiag = useCallback(async () => {
    const frontendFallback = {
      backend: false,
      python: false,
      ffmpeg: false,
      memory: false,
      storage: false,
      gpu: false,
      frontend: getFrontendDiag('正在检测后端...'),
    };
    setBackendDiag(frontendFallback);

    try {
      const res = await fetch('/api/v1/diag');
      if (res.ok) {
        const data = await res.json();
        data.frontend = getFrontendDiag();
        setBackendDiag(data);
        setBackendAvailable(data.backend);
        setConnectionStatus(data.backend ? 'connected' : 'disconnected');
      } else {
        const errorDetail = `HTTP ${res.status} ${res.statusText}`;
        setBackendDiag({
          backend: false,
          python: false,
          ffmpeg: false,
          memory: false,
          storage: false,
          gpu: false,
          frontend: getFrontendDiag(errorDetail),
        });
        setBackendAvailable(false);
        setConnectionStatus('unstable');
      }
    } catch (err) {
      const errorDetail = err instanceof Error ? `${err.name}: ${err.message}` : 'Network request failed';
      setBackendDiag({
        backend: false,
        python: false,
        ffmpeg: false,
        memory: false,
        storage: false,
        gpu: false,
        frontend: getFrontendDiag(errorDetail),
      });
      setBackendAvailable(false);
      setConnectionStatus('disconnected');
    }
  }, []);

  useEffect(() => {
    const cleanup = setupNetworkInterceptor(triggerUpstream, handleResponseSuccess);
    return cleanup;
  }, [triggerUpstream, handleResponseSuccess]);

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
        connectionStatus,
        hasUpstreamActivity,
        hasDownstreamActivity,
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
