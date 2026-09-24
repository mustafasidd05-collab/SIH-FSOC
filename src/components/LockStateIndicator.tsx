import React from 'react';
import { TrackState, STATE_COLORS } from '../types/contracts';

interface LockStateIndicatorProps {
  state: TrackState;
}

export const LockStateIndicator: React.FC<LockStateIndicatorProps> = ({ state }) => {
  const color = STATE_COLORS[state];
  const isLost = state === TrackState.LOST;

  return (
    <div
      id="lock-state-banner"
      className={`relative w-[230px] h-[80px] border flex flex-col items-center justify-center transition-colors duration-200 select-none ${
        isLost ? 'animate-lost-blink' : ''
      }`}
      style={{
        borderColor: color,
        backgroundColor: `${color}1F`, // ~12% alpha (0x1F = 31 / 255)
      }}
    >
      <div className="absolute top-1 left-2 text-[9px] font-mono tracking-widest uppercase opacity-70" style={{ color }}>
        LOCK STATUS
      </div>
      <div
        className="font-mono-telemetry text-3xl font-extrabold tracking-wider"
        style={{ color }}
      >
        {state}
      </div>
      <div className="absolute bottom-1 right-2 flex items-center gap-1">
        <span
          className="w-2 h-2 rounded-full inline-block"
          style={{ backgroundColor: color }}
        />
        <span className="text-[9px] font-mono uppercase opacity-70" style={{ color }}>
          {state === TrackState.TRACK ? 'CLOSED-LOOP' : state === TrackState.SEARCH ? 'SCANNING' : 'ACTIVE'}
        </span>
      </div>
    </div>
  );
};
