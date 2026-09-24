import React, { useRef } from 'react';
import { CameraState, TelemetryPacket, TrackState, STATE_COLORS } from '../types/contracts';

interface VideoCanvasProps {
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
  camera: CameraState;
  packet: TelemetryPacket | null;
  onSelectTarget: (px: number, py: number) => void;
}

export const VideoCanvas: React.FC<VideoCanvasProps> = ({
  canvasRef,
  camera,
  packet,
  onSelectTarget,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    if (clickX >= 0 && clickX <= rect.width && clickY >= 0 && clickY <= rect.height) {
      const scaleX = camera.width_px / rect.width;
      const scaleY = camera.height_px / rect.height;
      const imgX = clickX * scaleX;
      const imgY = clickY * scaleY;
      onSelectTarget(imgX, imgY);
    }
  };

  const state = packet?.track_state ?? TrackState.SEARCH;
  const accentColor = STATE_COLORS[state];

  return (
    <div
      ref={containerRef}
      id="video-feed-container"
      onClick={handleClick}
      className="relative w-full h-full bg-[#0A0D0F] flex items-center justify-center cursor-crosshair overflow-hidden border border-[#232C33]"
      title="Click anywhere to acquire optical beacon"
    >
      <canvas
        ref={canvasRef}
        width={camera.width_px}
        height={camera.height_px}
        className="max-w-full max-h-full object-contain pointer-events-none"
      />

      {/* 4-Corner Mission-Control HUD Overlays */}
      <div className="absolute inset-0 pointer-events-none p-3.5 flex flex-col justify-between font-mono-telemetry text-[11px] select-none">
        {/* Top Bar Overlay */}
        <div className="flex justify-between items-start">
          <div className="bg-[#0C1013]/85 backdrop-blur-xs border border-[#232C33] px-2.5 py-1.5 rounded-xs space-y-0.5">
            <div className="text-[#93A0A8] flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-[#00E676] animate-pulse"></span>
              <span>SENSOR 640x480</span>
              <span className="text-[#5B6770]">|</span>
              <span className="text-[#D9E0E4]">FOV 4.0° x 3.0°</span>
            </div>
            <div className="text-[10px] text-[#5B6770]">
              RANGE: 1000m SLANT | GNOMONIC
            </div>
          </div>

          <div className="bg-[#0C1013]/85 backdrop-blur-xs border border-[#232C33] px-2.5 py-1.5 rounded-xs text-right space-y-0.5">
            <div className="text-[#D9E0E4] font-bold">
              FRAME #{packet ? packet.frame_id.toString().padStart(6, '0') : '000000'}
            </div>
            <div className="text-[10px] text-[#93A0A8]">
              SYS FPS: <span className="text-[#00E676] font-bold">{packet ? packet.fps.toFixed(1) : '30.0'}</span>
              <span className="text-[#5B6770]"> | </span>
              DT: {(packet ? packet.loop_time_s * 1000 : 16.7).toFixed(1)}ms
            </div>
          </div>
        </div>

        {/* Center Target Acquisition Hint (in SEARCH state) */}
        {state === TrackState.SEARCH && (
          <div className="self-center bg-[#0C1013]/80 border border-[#FFB300]/40 text-[#FFB300] px-3 py-1 text-xs rounded tracking-wider flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#FFB300] animate-ping" />
            SCANNING FOR OPTICAL BEACON — CLICK TO TARGET
          </div>
        )}

        {/* Bottom Bar Overlay */}
        <div className="flex justify-between items-end">
          <div className="bg-[#0C1013]/85 backdrop-blur-xs border border-[#232C33] px-2.5 py-1.5 rounded-xs space-y-0.5">
            <div className="text-[#93A0A8]">
              GIMBAL PAN: <span className="text-[#D9E0E4] font-bold">{(camera.pan_rad * (180 / Math.PI)).toFixed(2)}°</span>
              <span className="text-[#5B6770]"> | </span>
              TILT: <span className="text-[#D9E0E4] font-bold">{(camera.tilt_rad * (180 / Math.PI)).toFixed(2)}°</span>
            </div>
            <div className="text-[10px] text-[#5B6770]">
              LIMITS: ±90.0° AZ / ±90.0° EL
            </div>
          </div>

          <div className="bg-[#0C1013]/85 backdrop-blur-xs border border-[#232C33] px-2.5 py-1.5 rounded-xs text-right space-y-0.5">
            <div className="flex items-center justify-end gap-1.5">
              <span className="text-[#93A0A8]">LOCK RATE:</span>
              <span className="font-bold" style={{ color: accentColor }}>
                {packet ? (packet.lock_fraction * 100).toFixed(1) : '0.0'}%
              </span>
            </div>
            <div className="text-[10px] text-[#93A0A8]">
              ACQ TIME: <span className="text-[#D9E0E4] font-mono">{packet && !isNaN(packet.acquisition_time_s) ? `${packet.acquisition_time_s.toFixed(2)}s` : 'N/A'}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
