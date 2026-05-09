import React, { useEffect, useRef } from 'react';

interface SpectrumVisualizerProps {
  analyser: AnalyserNode | null;
  label?: string;
  color?: string;
}

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
    const dataArray = new Uint8Array(bufferLength);

    const ensureCanvasSize = () => {
      const container = containerRef.current;
      const actualWidth = container ? container.clientWidth : 400;
      const actualHeight = 120;
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

    const ensureGradient = (actualHeight: number) => {
      if (gradientRef.current && lastColorRef.current === color) return gradientRef.current;
      const g = ctx.createLinearGradient(0, 0, 0, actualHeight);
      g.addColorStop(0, color + '80');
      g.addColorStop(1, color);
      gradientRef.current = g;
      lastColorRef.current = color;
      return g;
    };

    const draw = (timestamp: number) => {
      animationFrameRef.current = requestAnimationFrame(draw);

      if (timestamp - lastFrameTimeRef.current < 33) return;
      lastFrameTimeRef.current = timestamp;

      analyser.getByteFrequencyData(dataArray);

      const { width, height } = ensureCanvasSize();
      const gradient = ensureGradient(height);

      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = '#0A1A2F';
      ctx.fillRect(0, 0, width, height);

      const barWidth = (width / bufferLength) * 2.5;
      let x = 0;

      ctx.beginPath();
      for (let i = 0; i < bufferLength; i++) {
        const barHeight = (dataArray[i] / 255) * height;
        ctx.rect(x, height - barHeight, barWidth - 2, barHeight);
        x += barWidth;
      }
      ctx.fillStyle = gradient;
      ctx.fill();
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
