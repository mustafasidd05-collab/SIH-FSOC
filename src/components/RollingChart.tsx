import React, { useRef, useEffect } from 'react';

interface RollingChartProps {
  id?: string;
  title: string;
  value: number;
  timestamp: number;
  minVal?: number;
  maxVal?: number;
  unit?: string;
  lineColorHex?: string;
  capacity?: number;
}

export const RollingChart: React.FC<RollingChartProps> = ({
  id,
  title,
  value,
  timestamp,
  minVal = 0,
  maxVal = 100,
  unit = '',
  lineColorHex = '#00E676',
  capacity = 120,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const dataRef = useRef<Array<{ t: number; v: number }>>([]);

  useEffect(() => {
    if (!isNaN(value)) {
      dataRef.current.push({ t: timestamp, v: value });
      if (dataRef.current.length > capacity) {
        dataRef.current.shift();
      }
    }

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = canvas.width;
    const h = canvas.height;

    // Background
    ctx.fillStyle = '#0C1013';
    ctx.fillRect(0, 0, w, h);

    // Border
    ctx.strokeStyle = '#232C33';
    ctx.lineWidth = 1;
    ctx.strokeRect(0.5, 0.5, w - 1, h - 1);

    // Horizontal gridlines (25%, 50%, 75%)
    ctx.strokeStyle = 'rgba(35, 44, 51, 0.7)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 1; i <= 3; i++) {
      const y = Math.round((h / 4) * i) + 0.5;
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
    }
    ctx.stroke();

    const data = dataRef.current;
    if (data.length > 1) {
      // Draw trendline
      ctx.beginPath();
      ctx.strokeStyle = lineColorHex;
      ctx.lineWidth = 1.75;

      const range = maxVal - minVal || 1;

      data.forEach((pt, i) => {
        const x = (i / (capacity - 1)) * (w - 10) + 5;
        const clampedV = Math.max(minVal, Math.min(maxVal, pt.v));
        const normalizedY = 1.0 - (clampedV - minVal) / range;
        const y = normalizedY * (h - 22) + 16;

        if (i === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      });
      ctx.stroke();

      // Subtle gradient fill under curve
      const lastX = ((data.length - 1) / (capacity - 1)) * (w - 10) + 5;
      const firstX = (0 / (capacity - 1)) * (w - 10) + 5;
      ctx.lineTo(lastX, h - 2);
      ctx.lineTo(firstX, h - 2);
      ctx.closePath();

      const fillGrad = ctx.createLinearGradient(0, 16, 0, h);
      fillGrad.addColorStop(0, `${lineColorHex}26`);
      fillGrad.addColorStop(1, `${lineColorHex}00`);
      ctx.fillStyle = fillGrad;
      ctx.fill();
    }
  }, [value, timestamp, minVal, maxVal, lineColorHex, capacity]);

  const displayVal = !isNaN(value) ? value.toFixed(1) : '--';

  return (
    <div id={id} className="relative w-full h-[85px] bg-[#0C1013] border border-[#232C33] flex flex-col justify-between p-1.5 select-none">
      <div className="flex items-center justify-between z-10 pointer-events-none px-1">
        <span className="text-[10px] font-mono tracking-wider font-semibold text-[#93A0A8] uppercase">
          {title}
        </span>
        <span
          className="text-xs font-mono font-bold"
          style={{ color: lineColorHex }}
        >
          {displayVal}{unit}
        </span>
      </div>
      <canvas
        ref={canvasRef}
        width={240}
        height={60}
        className="w-full h-[60px] block"
      />
    </div>
  );
};
