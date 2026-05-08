import React, { useState, useEffect, useRef } from 'react';

interface BuildInfoData {
  buildTime: string;
  mode: 'development' | 'production';
  isDevServer: boolean;
  lastHmrTime: string | null;
}

export function BuildInfo() {
  const [info, setInfo] = useState<BuildInfoData | null>(null);
  const [hmrTime, setHmrTime] = useState<string | null>(null);
  const [clickCount, setClickCount] = useState(0);
  const clickTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    try {
      // 检测当前模式
      const isDev = typeof import.meta !== 'undefined' && import.meta.env?.DEV === true;
      const isDevServer = typeof import.meta !== 'undefined' && import.meta.env?.MODE === 'development';

      // 获取构建时间（从 Vite 构建时注入的常量）
      let buildTime: string;
      try {
        buildTime = typeof __BUILD_TIME__ === 'string' ? __BUILD_TIME__ : new Date().toISOString();
      } catch {
        buildTime = new Date().toISOString();
      }

      setInfo({
        buildTime,
        mode: isDev ? 'development' : 'production',
        isDevServer,
        lastHmrTime: null,
      });

      // 开发模式下监听 HMR
      if (isDev && typeof import.meta !== 'undefined' && import.meta.hot) {
        import.meta.hot.on('vite:beforeUpdate', () => {
          setHmrTime(new Date().toLocaleTimeString());
        });
      }
    } catch (e) {
      // 如果出错，就不显示这个组件，避免影响整个页面
      console.error('BuildInfo error:', e);
    }
    return () => {
      if (clickTimerRef.current) {
        clearTimeout(clickTimerRef.current);
      }
    };
  }, []);

  if (!info) return null;

  const formatTime = (timeStr: string) => {
    try {
      const date = new Date(timeStr);
      return date.toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    } catch {
      return timeStr;
    }
  };

  const handleClick = () => {
    const newCount = clickCount + 1;
    setClickCount(newCount);
    if (clickTimerRef.current) {
      clearTimeout(clickTimerRef.current);
    }
    clickTimerRef.current = setTimeout(() => {
      setClickCount(0);
    }, 2000);
    if (newCount >= 3) {
      setClickCount(0);
      const vc = (window as any).__vconsole__;
      if (vc && vc.show) {
        vc.show();
      }
    }
  };

  return (
    <div className="fixed bottom-2 left-2 z-50" onClick={handleClick} style={{ cursor: 'pointer' }} title="连续点击3次打开调试面板">
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
