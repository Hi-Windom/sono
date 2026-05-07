import React, { useState, useEffect } from 'react';

interface BuildInfoData {
  buildTime: string;
  mode: 'development' | 'production';
  isDevServer: boolean;
  lastHmrTime: string | null;
}

export function BuildInfo() {
  const [info, setInfo] = useState<BuildInfoData | null>(null);
  const [hmrTime, setHmrTime] = useState<string | null>(null);

  useEffect(() => {
    // 检测当前模式
    const isDev = import.meta.env.DEV;
    const isDevServer = import.meta.env.MODE === 'development';
    
    // 获取构建时间（从 Vite 的 import.meta.env）
    const buildTime = new Date().toISOString();
    
    setInfo({
      buildTime,
      mode: isDev ? 'development' : 'production',
      isDevServer,
      lastHmrTime: null,
    });

    // 开发模式下监听 HMR
    if (isDev && import.meta.hot) {
      import.meta.hot.on('vite:beforeUpdate', () => {
        setHmrTime(new Date().toLocaleTimeString());
      });
    }
  }, []);

  if (!info) return null;

  const formatTime = (timeStr: string) => {
    const date = new Date(timeStr);
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  return (
    <div className="fixed bottom-2 left-2 z-50">
      <div className="bg-black/70 backdrop-blur-sm text-gray-400 text-[10px] px-2 py-1 rounded border border-gray-700/50">
        <div className="flex items-center gap-2">
          <span 
            className={`w-1.5 h-1.5 rounded-full ${
              info.mode === 'development' ? 'bg-yellow-500' : 'bg-green-500'
            }`}
            title={info.mode === 'development' ? '开发模式' : '生产模式'}
          />
          <span>
            {info.mode === 'development' ? '开发模式' : '静态部署'}
          </span>
          <span className="text-gray-600">|</span>
          <span>构建: {formatTime(info.buildTime)}</span>
          {info.mode === 'development' && hmrTime && (
            <>
              <span className="text-gray-600">|</span>
              <span className="text-yellow-400">热重载: {hmrTime}</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
