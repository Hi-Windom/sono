import React, { useEffect, useRef } from 'react';

interface SpectrumVisualizerProps {
  analyser: AnalyserNode | null;
  label?: string;
  color?: string;
}

const BAR_COUNT = 32;
const PADDING_LEFT = 36;
const PADDING_BOTTOM = 20;
const PADDING_TOP = 4;
const PADDING_RIGHT = 4;

const FREQ_LABELS = ['100', '500', '1k', '2k', '4k', '8k', '16k'];
const DB_LABELS = ['0', '-10', '-20', '-30', '-40', '-50'];

export function SpectrumVisualizer({
  analyser,
  label,
  color = '#00D9FF',
}: SpectrumVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationFrameRef = useRef<number>();
  const containerRef = useRef<HTMLDivElement>(null);
  const lastSizeRef = useRef({ width: 0, height: 0 });
  const gradientRef = useRef<CanvasGradient | null>(null);
  const lastColorRef = useRef<string>('');
  const lastFrameTimeRef = useRef(0);

  useEffect(() => {
    if (!analyser || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    analyser.fftSize = 256;
    const bufferLength = analyser.frequencyBinCount;
    const rawData = new Uint8Array(bufferLength);

    const ensureCanvasSize = () => {
      const container = containerRef.current;
      const actualWidth = container ? container.clientWidth : 400;
      const actualHeight = 160;
      if (lastSizeRef.current.width !== actualWidth || lastSizeRef.current.height !== actualHeight) {
        canvas.width = actualWidth * window.devicePixelRatio;
        canvas.height = actualHeight * window.devicePixelRatio;
        canvas.style.width = actualWidth + 'px';
        canvas.style.height = actualHeight + 'px';
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
        lastSizeRef.current = { width: actualWidth, height: actualHeight };
        gradientRef.current = null;
      }
      return { width: actualWidth, height: actualHeight };
    };

    const ensureGradient = (barAreaHeight: number) => {
      if (gradientRef.current && lastColorRef.current === color) return gradientRef.current;
      const g = ctx.createLinearGradient(0, 0, 0, barAreaHeight);
      g.addColorStop(0, color + '40');
      g.addColorStop(0.5, color + '90');
      g.addColorStop(1, color);
      gradientRef.current = g;
      lastColorRef.current = color;
      return g;
    };

    const binToFreq = (bin: number) => (bin * analyser.context.sampleRate) / analyser.fftSize;

    const draw = (timestamp: number) => {
      animationFrameRef.current = requestAnimationFrame(draw);

      if (timestamp - lastFrameTimeRef.current < 11) return;
      lastFrameTimeRef.current = timestamp;

      analyser.getByteFrequencyData(rawData);

      const { width, height } = ensureCanvasSize();
      const barAreaWidth = width - PADDING_LEFT - PADDING_RIGHT;
      const barAreaHeight = height - PADDING_BOTTOM - PADDING_TOP;
      const gradient = ensureGradient(barAreaHeight);

      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = '#0A1A2F';
      ctx.fillRect(0, 0, width, height);

      ctx.strokeStyle = 'rgba(255,255,255,0.06)';
      ctx.lineWidth = 0.5;
      for (let i = 1; i <= 5; i++) {
        const y = PADDING_TOP + (barAreaHeight / 6) * i;
        ctx.beginPath();
        ctx.moveTo(PADDING_LEFT, y);
        ctx.lineTo(width - PADDING_RIGHT, y);
        ctx.stroke();
      }

      const step = Math.max(1, Math.floor(bufferLength / BAR_COUNT));
      const barWidth = (barAreaWidth / BAR_COUNT) * 0.75;
      const barGap = (barAreaWidth / BAR_COUNT) * 0.25;

      ctx.beginPath();
      for (let i = 0; i < BAR_COUNT; i++) {
        let sum = 0;
        let count = 0;
        for (let j = 0; j < step; j++) {
          const idx = i * step + j;
          if (idx < bufferLength) {
            sum += rawData[idx];
            count++;
          }
        }
        const avg = count > 0 ? sum / count : 0;
        const barHeight = (avg / 255) * barAreaHeight;
        const x = PADDING_LEFT + i * (barWidth + barGap);
        ctx.rect(x, PADDING_TOP + barAreaHeight - barHeight, barWidth, barHeight);
      }
      ctx.fillStyle = gradient;
      ctx.fill();

      ctx.fillStyle = 'rgba(255,255,255,0.3)';
      ctx.font = '9px system-ui';
      ctx.textAlign = 'center';
      for (let i = 0; i < FREQ_LABELS.length; i++) {
        const x = PADDING_LEFT + (barAreaWidth / (FREQ_LABELS.length - 1)) * i;
        ctx.fillText(FREQ_LABELS[i], x, height - 4);
      }

      ctx.textAlign = 'right';
      for (let i = 0; i < DB_LABELS.length; i++) {
        const y = PADDING_TOP + (barAreaHeight / (DB_LABELS.length - 1)) * i;
        ctx.fillText(DB_LABELS[i], PADDING_LEFT - 4, y + 3);
      }
    };

    draw(0);

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [analyser, color]);

  return (
    <div className="w-full">
      {label && (
        <div className="mb-2 flex items-center gap-2">
          <span className="text-white font-medium text-sm">{label}</span>
        </div>
      )}
      <div ref={containerRef} className="w-full bg-primary/50 rounded-xl overflow-hidden">
        <canvas ref={canvasRef} />
      </div>
    </div>
  );
}
