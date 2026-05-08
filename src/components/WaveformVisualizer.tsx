import React, { useEffect, useRef, useCallback } from 'react';

interface WaveformVisualizerProps {
  audioBuffer: AudioBuffer | null;
  color?: string;
  label?: string;
  currentTime?: number;
  duration?: number;
  onSeek?: (time: number) => void;
}

export function WaveformVisualizer({
  audioBuffer,
  color = '#00D9FF',
  label,
  currentTime = 0,
  duration = 0,
  onSeek,
}: WaveformVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const waveformDataRef = useRef<{ min: number[]; max: number[] } | null>(null);

  // 计算波形数据（同步）
  function computeWaveformData(buffer: AudioBuffer, width: number): { min: number[]; max: number[] } {
    const channelData = buffer.getChannelData(0);
    const samplesPerPixel = Math.max(1, Math.floor(channelData.length / width));

    const minData: number[] = [];
    const maxData: number[] = [];

    let maxSample = 0;
    for (let i = 0; i < channelData.length; i++) {
      maxSample = Math.max(maxSample, Math.abs(channelData[i]));
    }
    const normalization = maxSample > 0.05 ? 1 / maxSample : 20;

    for (let x = 0; x < width; x++) {
      let min = 1.0;
      let max = -1.0;

      for (let i = 0; i < samplesPerPixel; i++) {
        const index = x * samplesPerPixel + i;
        if (index < channelData.length) {
          const val = channelData[index] * normalization;
          min = Math.min(min, val);
          max = Math.max(max, val);
        }
      }

      minData.push(min);
      maxData.push(max);
    }

    return { min: minData, max: maxData };
  }

  // 绘制波形
  function drawWaveform() {
    if (!canvasRef.current || !audioBuffer) return;

    const container = containerRef.current;
    if (!container) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const actualWidth = container.clientWidth;
    const actualHeight = 140;

    // 计算波形数据
    const waveformData = computeWaveformData(audioBuffer, actualWidth);
    waveformDataRef.current = waveformData;

    canvas.width = actualWidth * window.devicePixelRatio;
    canvas.height = actualHeight * window.devicePixelRatio;
    canvas.style.width = actualWidth + 'px';
    canvas.style.height = actualHeight + 'px';
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

    const width = actualWidth;
    const height = actualHeight;
    const { min, max } = waveformData;

    const progressRatio = duration > 0 ? currentTime / duration : 0;
    const progressX = width * progressRatio;

    // 清空画布
    ctx.fillStyle = '#0A1A2F';
    ctx.fillRect(0, 0, width, height);

    // 已播放区域背景
    if (progressX > 0) {
      ctx.fillStyle = 'rgba(0, 217, 255, 0.08)';
      ctx.fillRect(0, 0, progressX, height);
    }

    // 渐变
    const playedGradient = ctx.createLinearGradient(0, 0, 0, height);
    playedGradient.addColorStop(0, '#00D9FFcc');
    playedGradient.addColorStop(0.5, '#00D9FF');
    playedGradient.addColorStop(1, '#00D9FFcc');

    // 未播放部分（灰色）
    ctx.fillStyle = 'rgba(100, 116, 139, 0.5)';
    for (let x = 0; x < width; x++) {
      if (x > progressX && x < min.length) {
        const y1 = (0.5 + min[x] * 0.4) * height;
        const y2 = (0.5 + max[x] * 0.4) * height;
        ctx.fillRect(x, y1, 1, y2 - y1 || 1);
      }
    }

    // 已播放部分（高亮）
    ctx.fillStyle = playedGradient;
    for (let x = 0; x < width; x++) {
      if (x <= progressX && x < min.length) {
        const y1 = (0.5 + min[x] * 0.4) * height;
        const y2 = (0.5 + max[x] * 0.4) * height;
        ctx.fillRect(x, y1, 1, y2 - y1 || 1);
      }
    }

    // 中心线
    ctx.strokeStyle = color + '22';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, height / 2);
    ctx.lineTo(width, height / 2);
    ctx.stroke();

    // 进度条背景
    ctx.fillStyle = 'rgba(0, 0, 0, 0.3)';
    ctx.fillRect(0, height - 4, width, 4);

    // 进度条
    ctx.fillStyle = color;
    ctx.fillRect(0, height - 4, progressX, 4);

    // 进度指示器
    if (progressX > 0 && progressX < width) {
      ctx.beginPath();
      ctx.arc(progressX, height - 2, 6, 0, Math.PI * 2);
      ctx.fillStyle = '#fff';
      ctx.fill();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.stroke();

      // 垂直线
      ctx.strokeStyle = color + '66';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(progressX, 0);
      ctx.lineTo(progressX, height - 8);
      ctx.stroke();
    }
  }

  // 关键：使用 key prop 强制重新挂载组件
  // 当 audioBuffer 变化时，React 会卸载旧组件并挂载新组件
  // 这确保画布总是使用最新的波形数据
  useEffect(() => {
    drawWaveform();
  });

  // 窗口大小变化时重绘
  useEffect(() => {
    const handleResize = () => {
      if (audioBuffer) {
        drawWaveform();
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [audioBuffer, currentTime, duration]);

  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!onSeek || !duration) return;

      const canvas = canvasRef.current;
      if (!canvas) return;

      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const ratio = Math.max(0, Math.min(1, x / rect.width));
      onSeek(duration * ratio);
    },
    [onSeek, duration]
  );

  return (
    <div ref={containerRef} className="relative w-full group">
      {label && (
        <div className="absolute top-2 left-2 text-xs text-gray-400 font-medium z-10 bg-black/50 px-2 py-1 rounded">
          {label}
        </div>
      )}

      {/* 时间显示 */}
      <div className="absolute top-2 right-2 text-xs text-gray-400 z-10 bg-black/50 px-2 py-1 rounded">
        {formatTime(currentTime)} / {formatTime(duration)}
      </div>

      <canvas
        ref={canvasRef}
        className="w-full bg-[#0A1A2F] rounded-lg cursor-pointer hover:ring-1 hover:ring-secondary/30 transition-all"
        style={{ height: '140px' }}
        onClick={handleClick}
      />

      {/* 悬停提示 */}
      <div className="absolute bottom-1 left-1/2 -translate-x-1/2 text-[10px] text-gray-500 opacity-0 group-hover:opacity-100 transition-opacity">
        点击波形跳转
      </div>
    </div>
  );
}

function formatTime(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}
