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

  // 预计算波形数据
  useEffect(() => {
    if (!audioBuffer) return;

    const channelData = audioBuffer.getChannelData(0);
    const container = containerRef.current;
    const width = container ? container.clientWidth : 800;
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

    waveformDataRef.current = { min: minData, max: maxData };
  }, [audioBuffer]);

  // 绘制波形和进度
  useEffect(() => {
    if (!canvasRef.current || !waveformDataRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const container = containerRef.current;
    const actualWidth = container ? container.clientWidth : 800;
    const actualHeight = 140;

    canvas.width = actualWidth * window.devicePixelRatio;
    canvas.height = actualHeight * window.devicePixelRatio;
    canvas.style.width = actualWidth + 'px';
    canvas.style.height = actualHeight + 'px';
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

    const width = actualWidth;
    const height = actualHeight;
    const { min, max } = waveformDataRef.current;

    // 计算进度位置
    const progressRatio = duration > 0 ? currentTime / duration : 0;
    const progressX = width * progressRatio;

    // 清空画布
    ctx.fillStyle = '#0A1A2F';
    ctx.fillRect(0, 0, width, height);

    // 绘制已播放区域背景
    if (progressX > 0) {
      ctx.fillStyle = 'rgba(0, 217, 255, 0.08)';
      ctx.fillRect(0, 0, progressX, height);
    }

    // 绘制波形
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, color + 'cc');
    gradient.addColorStop(0.5, color);
    gradient.addColorStop(1, color + 'cc');

    const playedGradient = ctx.createLinearGradient(0, 0, 0, height);
    playedGradient.addColorStop(0, '#00D9FFcc');
    playedGradient.addColorStop(0.5, '#00D9FF');
    playedGradient.addColorStop(1, '#00D9FFcc');

    // 绘制未播放部分（灰色）
    ctx.fillStyle = 'rgba(100, 116, 139, 0.5)';
    for (let x = 0; x < width; x++) {
      if (x > progressX) {
        const y1 = (0.5 + min[x] * 0.4) * height;
        const y2 = (0.5 + max[x] * 0.4) * height;
        ctx.fillRect(x, y1, 1, y2 - y1 || 1);
      }
    }

    // 绘制已播放部分（高亮）
    ctx.fillStyle = playedGradient;
    for (let x = 0; x < width; x++) {
      if (x <= progressX) {
        const y1 = (0.5 + min[x] * 0.4) * height;
        const y2 = (0.5 + max[x] * 0.4) * height;
        ctx.fillRect(x, y1, 1, y2 - y1 || 1);
      }
    }

    // 绘制中心线
    ctx.strokeStyle = color + '22';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, height / 2);
    ctx.lineTo(width, height / 2);
    ctx.stroke();

    // 绘制进度条背景
    ctx.fillStyle = 'rgba(0, 0, 0, 0.3)';
    ctx.fillRect(0, height - 4, width, 4);

    // 绘制进度条
    ctx.fillStyle = color;
    ctx.fillRect(0, height - 4, progressX, 4);

    // 绘制进度指示器（圆形手柄）
    if (progressX > 0 && progressX < width) {
      ctx.beginPath();
      ctx.arc(progressX, height - 2, 6, 0, Math.PI * 2);
      ctx.fillStyle = '#fff';
      ctx.fill();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.stroke();

      // 绘制垂直线
      ctx.strokeStyle = color + '66';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(progressX, 0);
      ctx.lineTo(progressX, height - 8);
      ctx.stroke();
    }
  }, [audioBuffer, color, currentTime, duration]);

  // 点击跳转
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
