import React, { useState } from 'react';
import { PerformanceLogger } from '../telemetry/performanceLogger';
import { TelemetryPacket, STATE_COLORS } from '../types/contracts';
import { X, Download, Upload, CheckCircle, AlertCircle, Clock, Activity } from 'lucide-react';

interface AnalyticsModalProps {
  isOpen: boolean;
  onClose: () => void;
  logger: PerformanceLogger;
}

export const AnalyticsModal: React.FC<AnalyticsModalProps> = ({ isOpen, onClose, logger }) => {
  const [filterState, setFilterState] = useState<string>('ALL');
  const [customPackets, setCustomPackets] = useState<TelemetryPacket[] | null>(null);

  if (!isOpen) return null;

  const packets = customPackets || logger.getPackets();
  const summary = logger.getSummary();

  const handleExport = () => {
    const jsonStr = logger.exportJSON();
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `performance_log_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (evt) => {
      try {
        const parsed = JSON.parse(evt.target?.result as string);
        if (parsed && Array.isArray(parsed.packets)) {
          setCustomPackets(parsed.packets);
        } else if (Array.isArray(parsed)) {
          setCustomPackets(parsed);
        }
      } catch (err) {
        alert('Invalid JSON performance log file');
      }
    };
    reader.readAsText(file);
  };

  const filteredPackets = packets.filter((p) => {
    if (filterState === 'ALL') return true;
    return p.track_state === filterState;
  });

  return (
    <div className="fixed inset-0 z-50 bg-[#0A0D0F]/85 backdrop-blur-sm flex items-center justify-center p-6 select-none animate-fadeIn">
      <div className="w-full max-w-5xl h-[85vh] bg-[#11161A] border border-[#232C33] rounded-lg shadow-2xl flex flex-col overflow-hidden text-[#D9E0E4]">
        {/* Header */}
        <div className="h-14 px-5 border-b border-[#232C33] flex items-center justify-between bg-[#0C1013]">
          <div className="flex items-center gap-3">
            <Activity className="text-[#00E676]" size={18} />
            <div>
              <h2 className="text-sm font-mono font-bold tracking-wider text-[#D9E0E4]">
                PERFORMANCE LOGS & TELEMETRY ANALYTICS
              </h2>
              <span className="text-[10px] text-[#93A0A8] font-mono">
                SIH 26169 COARSE-ALIGNMENT RUN EVALUATION
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <label className="py-1.5 px-3 bg-[#1A2126] hover:bg-[#232C33] border border-[#232C33] rounded font-mono text-xs text-[#93A0A8] hover:text-[#D9E0E4] flex items-center gap-1.5 cursor-pointer">
              <Upload size={13} />
              LOAD LOG
              <input type="file" accept=".json" onChange={handleImport} className="hidden" />
            </label>

            <button
              onClick={handleExport}
              className="py-1.5 px-3 bg-[#00E676] hover:bg-[#00E676]/90 text-[#0A0D0F] rounded font-mono text-xs font-bold flex items-center gap-1.5 cursor-pointer"
            >
              <Download size={13} />
              EXPORT JSON LOG
            </button>

            <button
              onClick={onClose}
              className="p-1.5 text-[#93A0A8] hover:text-[#D9E0E4] hover:bg-[#1A2126] rounded cursor-pointer ml-2"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* KPI Metrics Strip */}
        <div className="grid grid-cols-4 lg:grid-cols-8 gap-px bg-[#232C33] border-b border-[#232C33]">
          <div className="bg-[#0C1013] p-3 text-center">
            <span className="text-[9px] font-mono text-[#93A0A8] block uppercase">TOTAL FRAMES</span>
            <span className="text-base font-mono font-bold text-[#D9E0E4]">
              {summary.total_frames}
            </span>
          </div>
          <div className="bg-[#0C1013] p-3 text-center">
            <span className="text-[9px] font-mono text-[#93A0A8] block uppercase">DURATION</span>
            <span className="text-base font-mono font-bold text-[#D9E0E4]">
              {summary.duration_s.toFixed(1)}s
            </span>
          </div>
          <div className="bg-[#0C1013] p-3 text-center">
            <span className="text-[9px] font-mono text-[#93A0A8] block uppercase">AVERAGE FPS</span>
            <span className="text-base font-mono font-bold text-[#00E676]">
              {summary.average_fps.toFixed(1)}
            </span>
          </div>
          <div className="bg-[#0C1013] p-3 text-center">
            <span className="text-[9px] font-mono text-[#93A0A8] block uppercase">ACQUISITION TIME</span>
            <span className="text-base font-mono font-bold text-[#39C5CF]">
              {!isNaN(summary.acquisition_time_s) ? `${summary.acquisition_time_s.toFixed(2)}s` : 'N/A'}
            </span>
          </div>
          <div className="bg-[#0C1013] p-3 text-center">
            <span className="text-[9px] font-mono text-[#93A0A8] block uppercase">LOCK RETENTION</span>
            <span className="text-base font-mono font-bold text-[#00E676]">
              {(summary.lock_retention_rate * 100).toFixed(1)}%
            </span>
          </div>
          <div className="bg-[#0C1013] p-3 text-center">
            <span className="text-[9px] font-mono text-[#93A0A8] block uppercase">MEAN ERROR</span>
            <span className="text-base font-mono font-bold text-[#FFB300]">
              {summary.mean_error_px.toFixed(2)} px
            </span>
          </div>
          <div className="bg-[#0C1013] p-3 text-center">
            <span className="text-[9px] font-mono text-[#93A0A8] block uppercase">RMSE ERROR</span>
            <span className="text-base font-mono font-bold text-[#FFB300]">
              {summary.rmse_error_px.toFixed(2)} px
            </span>
          </div>
          <div className="bg-[#0C1013] p-3 text-center">
            <span className="text-[9px] font-mono text-[#93A0A8] block uppercase">MAX PEAK ERROR</span>
            <span className="text-base font-mono font-bold text-[#FF4D4F]">
              {summary.max_error_px.toFixed(1)} px
            </span>
          </div>
        </div>

        {/* Telemetry Packets Log Table */}
        <div className="flex-1 flex flex-col p-4 overflow-hidden space-y-3">
          <div className="flex items-center justify-between text-xs font-mono">
            <div className="flex items-center gap-2">
              <span className="text-[#93A0A8]">FILTER BY STATE:</span>
              {['ALL', 'TRACK', 'ACQUIRE', 'SEARCH', 'LOST', 'REACQUIRE'].map((st) => (
                <button
                  key={st}
                  onClick={() => setFilterState(st)}
                  className={`px-2 py-0.5 rounded text-[11px] cursor-pointer font-bold ${
                    filterState === st
                      ? 'bg-[#00E676] text-[#0A0D0F]'
                      : 'bg-[#1A2126] text-[#93A0A8] hover:text-[#D9E0E4]'
                  }`}
                >
                  {st}
                </button>
              ))}
            </div>
            <span className="text-[#93A0A8]">
              SHOWING {filteredPackets.length} OF {packets.length} PACKETS
            </span>
          </div>

          <div className="flex-1 overflow-y-auto border border-[#232C33] rounded bg-[#0C1013]">
            <table className="w-full text-left font-mono text-[11px]">
              <thead className="sticky top-0 bg-[#1A2126] text-[#93A0A8] uppercase text-[10px] border-b border-[#232C33]">
                <tr>
                  <th className="p-2.5">FRAME ID</th>
                  <th className="p-2.5">TIMESTAMP</th>
                  <th className="p-2.5">STATE</th>
                  <th className="p-2.5">ERROR X/Y (PX)</th>
                  <th className="p-2.5">RADIAL ERROR</th>
                  <th className="p-2.5">LOCK %</th>
                  <th className="p-2.5">FPS</th>
                  <th className="p-2.5">DT</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#232C33]/50">
                {filteredPackets.slice(-300).reverse().map((p) => {
                  const stateColor = STATE_COLORS[p.track_state];
                  const radialErr = !isNaN(p.error_px[0])
                    ? Math.hypot(p.error_px[0], p.error_px[1])
                    : NaN;

                  return (
                    <tr key={p.frame_id} className="hover:bg-[#11161A]">
                      <td className="p-2 font-bold text-[#D9E0E4]">
                        #{p.frame_id.toString().padStart(6, '0')}
                      </td>
                      <td className="p-2 text-[#93A0A8]">{p.timestamp_s.toFixed(3)}s</td>
                      <td className="p-2">
                        <span
                          className="px-1.5 py-0.5 rounded text-[10px] font-bold"
                          style={{
                            color: stateColor,
                            backgroundColor: `${stateColor}22`,
                          }}
                        >
                          {p.track_state}
                        </span>
                      </td>
                      <td className="p-2 text-[#D9E0E4]">
                        {!isNaN(p.error_px[0])
                          ? `${p.error_px[0].toFixed(1)}, ${p.error_px[1].toFixed(1)}`
                          : '--'}
                      </td>
                      <td className="p-2 font-bold" style={{ color: radialErr < 5 ? '#00E676' : '#FFB300' }}>
                        {!isNaN(radialErr) ? `${radialErr.toFixed(2)} px` : '--'}
                      </td>
                      <td className="p-2 text-[#93A0A8]">
                        {(p.lock_fraction * 100).toFixed(1)}%
                      </td>
                      <td className="p-2 text-[#D9E0E4]">{p.fps.toFixed(1)}</td>
                      <td className="p-2 text-[#93A0A8]">{(p.loop_time_s * 1000).toFixed(1)}ms</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
