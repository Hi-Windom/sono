import React from 'react';

interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

function clearAllPersistedState() {
  try { localStorage.removeItem('repair-session'); } catch {}
  try { localStorage.removeItem('app-settings'); } catch {}
  try {
    const dbs = ['audio-session-db', 'analysis-cache-db'];
    dbs.forEach(name => {
      const req = indexedDB.deleteDatabase(name);
      req.onsuccess = () => {};
      req.onerror = () => {};
    });
  } catch {}
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary] 渲染错误:', error, info.componentStack);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    window.location.reload();
  };

  handleClearAndReset = () => {
    clearAllPersistedState();
    this.setState({ hasError: false, error: null });
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="min-h-screen bg-gray-950 flex items-center justify-center p-6">
          <div className="max-w-md w-full bg-gray-900 border border-red-500/30 rounded-2xl p-6 text-center">
            <div className="text-4xl mb-3">⚠️</div>
            <h2 className="text-white text-lg font-bold mb-2">页面渲染出错</h2>
            <p className="text-gray-400 text-sm mb-4 break-all">{this.state.error?.message || '未知错误'}</p>
            <div className="flex flex-col gap-2">
              <button
                onClick={this.handleReset}
                className="px-4 py-2 bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 rounded-lg text-sm transition"
              >
                刷新页面
              </button>
              <button
                onClick={this.handleClearAndReset}
                className="px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg text-sm transition"
              >
                清除状态并刷新
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
