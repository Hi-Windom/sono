import React from 'react';

interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
  onError?: (error: Error, info: React.ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: React.ErrorInfo | null;
  showDetails: boolean;
  copyStatus: 'idle' | 'success' | 'error';
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
    this.state = { hasError: false, error: null, errorInfo: null, showDetails: false, copyStatus: 'idle' };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null, showDetails: false };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary] 渲染错误:', error, info.componentStack);
    this.setState({ errorInfo: info });
    if (this.props.onError) {
      this.props.onError(error, info);
    }
    try {
      fetch('/api/log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: `[Frontend Error] ${error.message}\n${info.componentStack}`,
          level: 'error',
        }),
      }).catch(() => {});
    } catch {}
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null, showDetails: false });
    window.location.reload();
  };

  handleClearAndReset = () => {
    clearAllPersistedState();
    this.setState({ hasError: false, error: null, errorInfo: null, showDetails: false });
    window.location.reload();
  };

  toggleDetails = () => {
    this.setState(prev => ({ showDetails: !prev.showDetails }));
  };

  copyError = async () => {
    const { error, errorInfo } = this.state;
    const errorText = `Error: ${error?.message || 'Unknown error'}\n\nStack:\n${error?.stack || 'N/A'}\n\nComponent Stack:\n${errorInfo?.componentStack || 'N/A'}`;
    const setCopyStatus = (status: 'success' | 'error') => {
      this.setState({ copyStatus: status });
      setTimeout(() => this.setState({ copyStatus: 'idle' }), 2000);
    };
    try {
      await navigator.clipboard.writeText(errorText);
      setCopyStatus('success');
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = errorText;
      document.body.appendChild(textarea);
      textarea.select();
      try {
        document.execCommand('copy');
        setCopyStatus('success');
      } catch {
        setCopyStatus('error');
      }
      document.body.removeChild(textarea);
    }
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="min-h-screen bg-gray-950 flex items-center justify-center p-6">
          <div className="max-w-lg w-full bg-gray-900 border border-red-500/30 rounded-2xl p-6">
            <div className="text-center mb-4">
              <div className="text-5xl mb-3">💥</div>
              <h2 className="text-white text-xl font-bold mb-2">页面渲染出错</h2>
              <p className="text-gray-400 text-sm break-words">
                {this.state.error?.message || '未知错误'}
              </p>
            </div>

            {this.state.showDetails && (
              <div className="mt-4 p-3 bg-gray-950 border border-gray-700 rounded-lg max-h-64 overflow-auto">
                <p className="text-red-400 text-xs font-mono whitespace-pre-wrap break-all">
                  {this.state.error?.stack || '无堆栈信息'}
                </p>
                {this.state.errorInfo?.componentStack && (
                  <>
                    <hr className="border-gray-700 my-2" />
                    <p className="text-yellow-400 text-xs font-mono whitespace-pre-wrap break-all">
                      Component Stack:
                      {'\n'}
                      {this.state.errorInfo.componentStack}
                    </p>
                  </>
                )}
              </div>
            )}

            <div className="flex flex-col gap-2 mt-5">
              <button
                onClick={this.handleReset}
                className="w-full px-4 py-2.5 bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 rounded-lg text-sm font-medium transition"
              >
                🔄 刷新页面
              </button>
              <button
                onClick={this.toggleDetails}
                className="w-full px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm transition"
              >
                {this.state.showDetails ? '隐藏详情' : '查看错误详情'}
              </button>
              {this.state.showDetails && (
                <>
                  <button
                    onClick={this.copyError}
                    className="w-full px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm transition"
                  >
                    📋 复制错误信息
                  </button>
                  {this.state.copyStatus === 'success' && (
                    <p className="text-green-400 text-xs text-center">✓ 已复制到剪贴板</p>
                  )}
                  {this.state.copyStatus === 'error' && (
                    <p className="text-red-400 text-xs text-center">✗ 复制失败，请手动复制</p>
                  )}
                </>
              )}
              <button
                onClick={this.handleClearAndReset}
                className="w-full px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg text-sm transition"
              >
                🗑️ 清除状态并刷新
              </button>
            </div>

            <p className="text-gray-500 text-xs text-center mt-4">
              如果问题持续出现，请联系技术支持并提供错误详情
            </p>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
