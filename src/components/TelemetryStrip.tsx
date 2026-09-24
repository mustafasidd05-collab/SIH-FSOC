import React from 'react';
import { TelemetryPacket, STATE_COLORS, TrackState } from '../types/contracts';

interface TelemetryStripProps {
  packet: TelemetryPacket | null;
}

export const TelemetryStrip: React.FC<TelemetryStripProps> = ({ packet }) => {
  const state = packet?.track_state ?? TrackState.SEARCH;
  const accentColor = STATE_COLORS[state];

  const errX = packet ? packet.error_px[0] : NaN;
  const errY = packet ? packet.error_px[1] : NaN;
  const errStr =
    !isNaN(errX) && !isNaN(errY)
      ? `${errX >= 0 ? '+' : ''}${errX.toFixed(1)} / ${errY >= 0 ? '+' : ''}${errY.toFixed(1)} px`
      : '-- / -- px';

  const azElStr = packet
    ? `${packet.error_az_rad >= 0 ? '+' : ''}${packet.error_az_rad.toFixed(4)} / ${packet.error_el_rad >= 0 ? '+' : ''}${packet.error_el_rad.toFixed(4)}`
    : '-- / --';

  const acqStr =
    packet && !isNaN(packet.acquisition_time_s)
      ? `${packet.acquisition_time_s.toFixed(2)}s`
      : 'N/A';

  return (
    <div
      id="telemetryStrip"
      className="h-[56px] bg-[#0C1013] border-t border-[#232C33] px-5 flex items-center justify-between font-mono-telemetry select-none"
    >
      <div className="flex items-center gap-7">
        <div className="flex flex-col">
          <span className="text-[10px] text-[#93A0A8] font-bold tracking-wider">FPS</span>
          <span className="text-sm font-bold text-[#D9E0E4]">
            {packet ? packet.fps.toFixed(1) : '--'}
          </span>
        </div>

        <div className="w-[1px] h-6 bg-[#232C33]" />

        <div className="flex flex-col">
          <span className="text-[10px] text-[#93A0A8] font-bold tracking-wider">LOOP TIME</span>
          <span className="text-sm font-bold text-[#D9E0E4]">
            {packet ? (packet.loop_time_s * 1000).toFixed(1) : '--'} ms
          </span>
        </div>

        <div className="w-[1px] h-6 bg-[#232C33]" />

        <div className="flex flex-col">
          <span className="text-[10px] text-[#93A0A8] font-bold tracking-wider">ERR X/Y</span>
          <span
            className="text-sm font-bold"
            style={{ color: !isNaN(errX) ? accentColor : '#D9E0E4' }}
          >
            {errStr}
          </span>
        </div>

        <div className="w-[1px] h-6 bg-[#232C33]" />

        <div className="flex flex-col">
          <span className="text-[10px] text-[#93A0A8] font-bold tracking-wider">AZ / EL RAD</span>
          <span className="text-sm font-bold text-[#D9E0E4]">
            {azElStr}
          </span>
        </div>

        <div className="w-[1px] h-6 bg-[#232C33]" />

        <div className="flex flex-col">
          <span className="text-[10px] text-[#93A0A8] font-bold tracking-wider">LOCK FRACTION</span>
          <span className="text-sm font-bold" style={{ color: accentColor }}>
            {packet ? `${(packet.lock_fraction * 100).toFixed(1)}%` : '--%'}
          </span>
        </div>

        <div className="w-[1px] h-6 bg-[#232C33]" />

        <div className="flex flex-col">
          <span className="text-[10px] text-[#93A0A8] font-bold tracking-wider">ACQ TIME</span>
          <span className="text-sm font-bold text-[#D9E0E4]">
            {acqStr}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <div className="text-right">
          <span className="text-[10px] text-[#93A0A8] block font-bold">FRAME ID</span>
          <span className="text-sm font-bold text-[#00E676]">
            #{packet ? packet.frame_id.toString().padStart(6, '0') : '000000'}
          </span>
        </div>
      </div>
    </div>
  );
};
