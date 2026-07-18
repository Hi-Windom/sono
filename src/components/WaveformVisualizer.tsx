import React, { useEffect, useRef, useCallback, useMemo } from 'react';

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
  const offscreenCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const lastWidthRef = useRef<number>(0);
  const lastHeightRef = useRef<number>(0);
  const lastProgressRef = useRef<number>(-1);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    audioBufferRef.current = audioBuffer;
  }, [audioBuffer]);

  useEffect(() => {
    peaksRef.current = waveformPeaks ?? null;
  }, [waveformPeaks]);

  const setupCanvas = useCallback(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return null;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;

    const width = container.clientWidth;
    const height = 140;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(dpr, dpr);
    return { ctx, width, height };
  }, []);

  const drawWaveformBase = useCallback((ctx: CanvasRenderingContext2D, width: number, height: number) => {
    const data = audioBufferRef.current ? audioBufferRef.current.getChannelData(0) : null;
    const peaks = peaksRef.current;

    ctx.fillStyle = '#0A1A2F';
    ctx.fillRect(0, 0, width, height);

    if (!data && !peaks) {
      ctx.strokeStyle = color + '22';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, height / 2);
      ctx.lineTo(width, height / 2);
      ctx.stroke();
      return;
    }

    if (data) {
      const isLongAudio = data.length > 48000 * 60 * 5;
      const step = isLongAudio
        ? Math.max(1, Math.floor(data.length / (width * 2)))
        : Math.max(1, Math.floor(data.length / width));
      const bufferKey = `${data.length}_${width}`;
      if (bufferKey !== lastBufferKeyRef.current) {
        let peak = 0;
        const peakStep = isLongAudio ? Math.max(1, Math.floor(data.length / 10000)) : 1;
        for (let i = 0; i < data.length; i += peakStep) {
          const abs = Math.abs(data[i]);
          if (abs > peak) peak = abs;
        }
        peakRef.current = peak > 0.05 ? 1 / peak : 20;
        lastBufferKeyRef.current = bufferKey;
      }
      const norm = peakRef.current;

      ctx.fillStyle = 'rgba(100, 116, 139, 0.5)';
      for (let x = 0; x < width; x++) {
        let mn = 1, mx = -1;
        const startIdx = x * step;
        const endIdx = Math.min(startIdx + step, data.length);
        for (let idx = startIdx; idx < endIdx; idx++) {
          const v = data[idx] * norm;
          if (v < mn) mn = v;
          if (v > mx) mx = v;
        }
        const y1 = (0.5 + mn * 0.4) * height;
        const y2 = (0.5 + mx * 0.4) * height;
        ctx.fillRect(x, y1, 1, Math.max(1, y2 - y1));
      }
    } else if (peaks && peaks.length > 0) {
      const numPeaks = peaks.length;
      let maxAbs = 0;
      for (let i = 0; i < numPeaks; i++) {
        const [mn, mx] = peaks[i];
        const abs = Math.max(Math.abs(mn), Math.abs(mx));
        if (abs > maxAbs) maxAbs = abs;
      }
      const norm = maxAbs > 0.05 ? 1 / maxAbs : 20;
      peakRef.current = norm;

      ctx.fillStyle = 'rgba(100, 116, 139, 0.5)';
      for (let x = 0; x < width; x++) {
        const peakIdx = Math.min(Math.floor(x / width * numPeaks), numPeaks - 1);
        const [mn, mx] = peaks[peakIdx];
        const y1 = (0.5 + mn * norm * 0.4) * height;
        const y2 = (0.5 + mx * norm * 0.4) * height;
        ctx.fillRect(x, y1, 1, Math.max(1, y2 - y1));
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
  }, [color]);

  const drawProgress = useCallback((ctx: CanvasRenderingContext2D, width: number, height: number, progressX: number) => {
    const data = audioBufferRef.current ? audioBufferRef.current.getChannelData(0) : null;
    const peaks = peaksRef.current;
    const norm = peakRef.current;

    if (progressX > 0) {
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, 0, progressX, height);
      ctx.clip();

      const playedGrad = ctx.createLinearGradient(0, 0, 0, height);
      playedGrad.addColorStop(0, color + 'cc');
      playedGrad.addColorStop(0.5, color);
      playedGrad.addColorStop(1, color + 'cc');
      ctx.fillStyle = playedGrad;

      if (data) {
        const isLongAudio = data.length > 48000 * 60 * 5;
        const step = isLongAudio
          ? Math.max(1, Math.floor(data.length / (width * 2)))
          : Math.max(1, Math.floor(data.length / width));

        const endX = Math.ceil(progressX);
        for (let x = 0; x < endX; x++) {
          let mn = 1, mx = -1;
          const startIdx = x * step;
          const endIdx = Math.min(startIdx + step, data.length);
          for (let idx = startIdx; idx < endIdx; idx++) {
            const v = data[idx] * norm;
            if (v < mn) mn = v;
            if (v > mx) mx = v;
          }
          const y1 = (0.5 + mn * 0.4) * height;
          const y2 = (0.5 + mx * 0.4) * height;
          ctx.fillRect(x, y1, 1, Math.max(1, y2 - y1));
        }
      } else if (peaks && peaks.length > 0) {
        const numPeaks = peaks.length;
        const endX = Math.ceil(progressX);
        for (let x = 0; x < endX; x++) {
          const peakIdx = Math.min(Math.floor(x / width * numPeaks), numPeaks - 1);
          const [mn, mx] = peaks[peakIdx];
          const y1 = (0.5 + mn * norm * 0.4) * height;
          const y2 = (0.5 + mx * norm * 0.4) * height;
          ctx.fillRect(x, y1, 1, Math.max(1, y2 - y1));
        }
      }

      ctx.restore();
    }

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
  }, [color]);

  const render = useCallback(() => {
    const setup = setupCanvas();
    if (!setup) return;
    const { ctx, width, height } = setup;
    const progressX = duration > 0 ? (currentTime / duration) * width : 0;

    const bufferKey = audioBufferRef.current
      ? `buf_${audioBufferRef.current.length}_${width}_${height}`
      : peaksRef.current
        ? `peaks_${peaksRef.current.length}_${width}_${height}`
        : `empty_${width}_${height}`;

    let needsRedrawBase = false;
    if (bufferKey !== lastBufferKeyRef.current || width !== lastWidthRef.current || height !== lastHeightRef.current) {
      needsRedrawBase = true;
      lastBufferKeyRef.current = bufferKey;
      lastWidthRef.current = width;
      lastHeightRef.current = height;
    }

    if (needsRedrawBase) {
      if (!offscreenCanvasRef.current) {
        offscreenCanvasRef.current = document.createElement('canvas');
      }
      const offCtx = offscreenCanvasRef.current.getContext('2d');
      if (offCtx) {
        offscreenCanvasRef.current.width = width * (window.devicePixelRatio || 1);
        offscreenCanvasRef.current.height = height * (window.devicePixelRatio || 1);
        offCtx.setTransform(1, 0, 0, 1, 0, 0);
        offCtx.scale(window.devicePixelRatio || 1, window.devicePixelRatio || 1);
        drawWaveformBase(offCtx, width, height);
      }
    }

    if (offscreenCanvasRef.current) {
      ctx.drawImage(offscreenCanvasRef.current, 0, 0, width, height);
    }

    drawProgress(ctx, width, height, progressX);
    lastProgressRef.current = progressX;
  }, [setupCanvas, drawWaveformBase, drawProgress, currentTime, duration]);

  useEffect(() => {
    let cancelled = false;
    const doRender = () => {
      if (cancelled) return;
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(render);
    };
    doRender();
    return () => {
      cancelled = true;
      cancelAnimationFrame(rafRef.current);
    };
  }, [audioBuffer, waveformPeaks, currentTime, duration, render]);

  useEffect(() => {
    const handleResize = () => {
      lastBufferKeyRef.current = '';
      render();
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [render]);

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
