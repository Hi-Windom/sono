import React, { useEffect, useRef } from 'react';

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
  label
}: WaveformVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!canvasRef.current || !audioBuffer) return;

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
    const channelData = audioBuffer.getChannelData(0);
    const samplesPerPixel = Math.max(1, Math.floor(channelData.length / width));

    ctx.fillStyle = '#0A1A2F';
    ctx.fillRect(0, 0, width, height);

    let maxSample = 0;
    for (let i = 0; i < channelData.length; i++) {
      maxSample = Math.max(maxSample, Math.abs(channelData[i]));
    }
    const normalization = maxSample > 0.05 ? 1 / maxSample : 20;

    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, color + 'cc');
    gradient.addColorStop(0.5, color);
    gradient.addColorStop(1, color + 'cc');

    ctx.fillStyle = gradient;

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

      const y1 = (0.5 + min * 0.4) * height;
      const y2 = (0.5 + max * 0.4) * height;

      ctx.fillRect(x, y1, 1, y2 - y1 || 1);
    }

    ctx.strokeStyle = color + '44';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, height / 2);
    ctx.lineTo(width, height / 2);
    ctx.stroke();
  }, [audioBuffer, color]);

  return (
    <div ref={containerRef} className="relative w-full">
      {label && (
        <div className="absolute top-2 left-2 text-xs text-gray-400 font-medium z-10">
          {label}
        </div>
      )}
      <canvas
        ref={canvasRef}
        className="w-full bg-[#0A1A2F] rounded-lg"
        style={{ height: '140px' }}
      />
    </div>
  );
}
