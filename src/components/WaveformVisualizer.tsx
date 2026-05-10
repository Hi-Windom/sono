import React, { useEffect, useRef, useCallback } from 'react';

interface WaveformVisualizerProps {
  audioBuffer: AudioBuffer | null;
  color?: string;
  label?: string;
  currentTime?: number;
  duration?: number;
  onSeek?: (time: number) => void;
  waveformPeaks?: number[][] | null;
}

export function WaveformVisualizer({
  audioBuffer,
  color = '#00D9FF',
  label,
  currentTime = 0,
  duration = 0,
  onSeek,
  waveformPeaks,
}: WaveformVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const audioBufferRef = useRef<AudioBuffer | null>(null);
  const peaksRef = useRef<number[][] | null>(null);
  const peakRef = useRef<number>(0);
  const lastBufferKeyRef = useRef<string>('');

  useEffect(() => {
    audioBufferRef.current = audioBuffer;
  }, [audioBuffer]);

  useEffect(() => {
    peaksRef.current = waveformPeaks ?? null;
  }, [waveformPeaks]);

  const drawWaveform = useCallback((ctx: CanvasRenderingContext2D, width: number, height: number, progressX: number) => {
    const data = audioBufferRef.current ? audioBufferRef.current.getChannelData(0) : null;
    const peaks = peaksRef.current;

    if (!data && !peaks) {
      ctx.fillStyle = '#0A1A2F';
      ctx.fillRect(0, 0, width, height);
      ctx.strokeStyle = color + '22';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, height / 2);
      ctx.lineTo(width, height / 2);
      ctx.stroke();
      ctx.fillStyle = 'rgba(0, 0, 0, 0.3)';
      ctx.fillRect(0, height - 4, width, 4);
      return true;
    }

    ctx.fillStyle = '#0A1A2F';
    ctx.fillRect(0, 0, width, height);

    if (progressX > 0) {
      ctx.fillStyle = color + '08';
      ctx.fillRect(0, 0, progressX, height);
    }

    if (data) {
      const isLongAudio = data.length > 48000 * 60 * 5;
      const step = isLongAudio
        ? Math.max(1, Math.floor(data.length / (width * 2)))
        : Math.max(1, Math.floor(data.length / width));
      const bufferKey = `${data.length}`;
      if (bufferKey !== lastBufferKeyRef.current) {
        let peak = 0;
        for (let i = 0; i < data.length; i += (isLongAudio ? 8 : 1)) peak = Math.max(peak, Math.abs(data[i]));
        peakRef.current = peak > 0.05 ? 1 / peak : 20;
        lastBufferKeyRef.current = bufferKey;
      }
      const norm = peakRef.current;

      ctx.fillStyle = 'rgba(100, 116, 139, 0.5)';
      for (let x = 0; x < width; x++) {
        if (x > progressX) {
          let mn = 1, mx = -1;
          for (let j = 0; j < step; j++) {
            const idx = x * step + j;
            if (idx < data.length) {
              const v = data[idx] * norm;
              if (v < mn) mn = v;
              if (v > mx) mx = v;
            }
          }
          const y1 = (0.5 + mn * 0.4) * height;
          const y2 = (0.5 + mx * 0.4) * height;
          ctx.fillRect(x, y1, 1, Math.max(1, y2 - y1));
        }
      }

      const playedGrad = ctx.createLinearGradient(0, 0, 0, height);
      playedGrad.addColorStop(0, color + 'cc');
      playedGrad.addColorStop(0.5, color);
      playedGrad.addColorStop(1, color + 'cc');
      ctx.fillStyle = playedGrad;
      for (let x = 0; x < width; x++) {
        if (x <= progressX) {
          let mn = 1, mx = -1;
          for (let j = 0; j < step; j++) {
            const idx = x * step + j;
            if (idx < data.length) {
              const v = data[idx] * norm;
              if (v < mn) mn = v;
              if (v > mx) mx = v;
            }
          }
          const y1 = (0.5 + mn * 0.4) * height;
          const y2 = (0.5 + mx * 0.4) * height;
          ctx.fillRect(x, y1, 1, Math.max(1, y2 - y1));
        }
      }
    } else if (peaks && peaks.length > 0) {
      const numPeaks = peaks.length;
      let maxAbs = 0;
      for (const [mn, mx] of peaks) {
        maxAbs = Math.max(maxAbs, Math.abs(mn), Math.abs(mx));
      }
      const norm = maxAbs > 0.05 ? 1 / maxAbs : 20;
      peakRef.current = norm;

      ctx.fillStyle = 'rgba(100, 116, 139, 0.5)';
      for (let x = 0; x < width; x++) {
        if (x > progressX) {
          const peakIdx = Math.min(Math.floor(x / width * numPeaks), numPeaks - 1);
          const [mn, mx] = peaks[peakIdx];
          const y1 = (0.5 + mn * norm * 0.4) * height;
          const y2 = (0.5 + mx * norm * 0.4) * height;
          ctx.fillRect(x, y1, 1, Math.max(1, y2 - y1));
        }
      }

      const playedGrad = ctx.createLinearGradient(0, 0, 0, height);
      playedGrad.addColorStop(0, color + 'cc');
      playedGrad.addColorStop(0.5, color);
      playedGrad.addColorStop(1, color + 'cc');
      ctx.fillStyle = playedGrad;
      for (let x = 0; x < width; x++) {
        if (x <= progressX) {
          const peakIdx = Math.min(Math.floor(x / width * numPeaks), numPeaks - 1);
          const [mn, mx] = peaks[peakIdx];
          const y1 = (0.5 + mn * norm * 0.4) * height;
          const y2 = (0.5 + mx * norm * 0.4) * height;
          ctx.fillRect(x, y1, 1, Math.max(1, y2 - y1));
        }
      }
    }

    ctx.strokeStyle = color + '22';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, height / 2);
    ctx.lineTo(width, height / 2);
    ctx.stroke();

    ctx.fillStyle = 'rgba(0, 0, 0, 0.3)';
    ctx.fillRect(0, height - 4, width, 4);
    ctx.fillStyle = color;
    ctx.fillRect(0, height - 4, progressX, 4);

    if (progressX > 0 && progressX < width) {
      ctx.beginPath();
      ctx.arc(progressX, height - 2, 6, 0, Math.PI * 2);
      ctx.fillStyle = '#fff';
      ctx.fill();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.strokeStyle = color + '66';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(progressX, 0);
      ctx.lineTo(progressX, height - 8);
      ctx.stroke();
    }

    return true;
  }, [color]);

  const setupCanvas = useCallback(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return null;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;

    const width = container.clientWidth;
    const height = 140;
    canvas.width = width * window.devicePixelRatio;
    canvas.height = height * window.devicePixelRatio;
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    return { ctx, width, height };
  }, []);

  useEffect(() => {
    const setup = setupCanvas();
    if (!setup) return;
    const { ctx, width, height } = setup;
    const progressX = duration > 0 ? (currentTime / duration) * width : 0;
    drawWaveform(ctx, width, height, progressX);
  }, [audioBuffer, waveformPeaks, setupCanvas, drawWaveform]);

  useEffect(() => {
    if (!audioBufferRef.current && !peaksRef.current) return;
    const setup = setupCanvas();
    if (!setup) return;
    const { ctx, width, height } = setup;
    const progressX = duration > 0 ? (currentTime / duration) * width : 0;
    drawWaveform(ctx, width, height, progressX);
  }, [currentTime, duration, setupCanvas, drawWaveform]);

  useEffect(() => {
    const handleResize = () => {
      if (!audioBufferRef.current && !peaksRef.current) return;
      const setup = setupCanvas();
      if (!setup) return;
      const { ctx, width, height } = setup;
      const progressX = duration > 0 ? (currentTime / duration) * width : 0;
      drawWaveform(ctx, width, height, progressX);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [currentTime, duration, setupCanvas, drawWaveform]);

  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!onSeek || !duration) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      onSeek(duration * ratio);
    },
    [onSeek, duration]
  );

  return (
    <div ref={containerRef} className="relative w-full group">
      {label && (
        <div className="absolute top-2 left-2 text-xs font-medium z-10 bg-black/50 px-2 py-1 rounded" style={{ color }}>
          {label}
        </div>
      )}
      <div className="absolute top-2 right-2 text-xs text-gray-400 z-10 bg-black/50 px-2 py-1 rounded">
        {formatTime(currentTime)} / {formatTime(duration)}
      </div>
      <canvas
        ref={canvasRef}
        className="w-full bg-[#0A1A2F] rounded-lg cursor-pointer hover:ring-1 hover:ring-secondary/30 transition-all"
        style={{ height: '140px' }}
        onClick={handleClick}
      />
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
