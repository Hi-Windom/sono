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

  useEffect(() => {
    if (!analyser || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    analyser.fftSize = 256;
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const draw = () => {
      animationFrameRef.current = requestAnimationFrame(draw);

      analyser.getByteFrequencyData(dataArray);

      const container = containerRef.current;
      const actualWidth = container ? container.clientWidth : 400;
      const actualHeight = 120;

      canvas.width = actualWidth * window.devicePixelRatio;
      canvas.height = actualHeight * window.devicePixelRatio;
      canvas.style.width = actualWidth + 'px';
      canvas.style.height = actualHeight + 'px';
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

      ctx.fillStyle = '#0A1A2F';
      ctx.fillRect(0, 0, actualWidth, actualHeight);

      const barWidth = (actualWidth / bufferLength) * 2.5;
      let x = 0;

      for (let i = 0; i < bufferLength; i++) {
        const barHeight = (dataArray[i] / 255) * actualHeight;

        const gradient = ctx.createLinearGradient(0, actualHeight - barHeight, 0, actualHeight);
        gradient.addColorStop(0, color);
        gradient.addColorStop(1, color + '80');

        ctx.fillStyle = gradient;
        ctx.fillRect(x, actualHeight - barHeight, barWidth - 2, barHeight);

        x += barWidth;
      }
    };

    draw();

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
