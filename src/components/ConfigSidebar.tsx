import React, { useState } from 'react';
import { DisturbanceConfig, SceneConfig, PIDGains } from '../types/contracts';
import { DISTURBANCE_PROFILES } from '../disturbance/pipeline';
import { Play, Pause, RotateCcw, BarChart3, Presentation, Sliders, Eye, Sparkles } from 'lucide-react';

interface ConfigSidebarProps {
  isRunning: boolean;
  onToggleRun: () => void;
  onReset: () => void;
  sceneConfig: SceneConfig;
  onUpdateScene: (cfg: SceneConfig) => void;
  disturbanceConfig: DisturbanceConfig;
  onUpdateDisturbance: (cfg: DisturbanceConfig) => void;
  pidGains: PIDGains;
  onUpdatePID: (gains: PIDGains) => void;
  onOpenAnalytics: () => void;
  onOpenPresentation: () => void;
}

export const ConfigSidebar: React.FC<ConfigSidebarProps> = ({
  isRunning,
  onToggleRun,
  onReset,
  sceneConfig,
  onUpdateScene,
  disturbanceConfig,
  onUpdateDisturbance,
  pidGains,
  onUpdatePID,
  onOpenAnalytics,
  onOpenPresentation,
}) => {
  const [activeTab, setActiveTab] = useState<'sim' | 'pid'>('sim');

  const handleProfileChange = (profile: 'mild' | 'moderate' | 'severe' | 'custom') => {
    if (profile === 'custom') {
      onUpdateDisturbance({ ...disturbanceConfig, profile: 'custom' });
    } else {
      const p = DISTURBANCE_PROFILES[profile];
      onUpdateDisturbance({
        ...disturbanceConfig,
        profile,
        vibration_sigma_urad: p.vibration_sigma_urad,
        turbulence_index: p.turbulence_index,
        sensor_noise_sigma: p.sensor_noise_sigma,
      });
    }
  };

  return (
    <aside
      id="configPanel"
      className="w-[310px] h-full bg-[#11161A] border-r border-[#232C33] flex flex-col justify-between overflow-hidden select-none text-[#D9E0E4]"
    >
      {/* Scrollable controls */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between pb-2 border-b border-[#232C33]">
          <div>
            <h2 className="text-xs font-mono font-bold tracking-widest text-[#00E676] uppercase">
              MISSION CONTROL
            </h2>
            <p className="text-[10px] text-[#93A0A8]">FSOC COARSE-ALIGNMENT</p>
          </div>
          <div className="flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${
                isRunning ? 'bg-[#00E676] animate-pulse' : 'bg-[#FF4D4F]'
              }`}
            />
            <span className="text-[10px] font-mono font-semibold text-[#93A0A8]">
              {isRunning ? 'SIM RUNNING' : 'PAUSED'}
            </span>
          </div>
        </div>

        {/* Primary Sim Controls */}
        <div className="grid grid-cols-3 gap-2">
          <button
            id="btn-run-simulation"
            onClick={onToggleRun}
            className={`col-span-2 py-2 px-3 rounded font-mono text-xs font-bold flex items-center justify-center gap-2 cursor-pointer transition-colors shadow-sm ${
              isRunning
                ? 'bg-[#1A2126] text-[#FFB300] border border-[#FFB300]/50 hover:bg-[#232C33]'
                : 'bg-[#00E676] text-[#0A0D0F] hover:bg-[#00E676]/90'
            }`}
          >
            {isRunning ? <Pause size={14} /> : <Play size={14} />}
            {isRunning ? 'PAUSE' : 'START SIMULATION'}
          </button>

          <button
            id="btn-reset-simulation"
            onClick={onReset}
            className="py-2 px-2 bg-[#1A2126] hover:bg-[#232C33] border border-[#232C33] rounded font-mono text-xs text-[#93A0A8] hover:text-[#D9E0E4] flex items-center justify-center gap-1 cursor-pointer transition-colors"
            title="Reset Simulation & Kalman Filter"
          >
            <RotateCcw size={13} />
            RESET
          </button>
        </div>

        {/* Tab switch between Sim Controls and PID Tuning */}
        <div className="flex border-b border-[#232C33] text-xs font-mono">
          <button
            onClick={() => setActiveTab('sim')}
            className={`flex-1 py-1.5 text-center font-bold transition-colors cursor-pointer ${
              activeTab === 'sim'
                ? 'text-[#00E676] border-b-2 border-[#00E676] bg-[#0C1013]/50'
                : 'text-[#93A0A8] hover:text-[#D9E0E4]'
            }`}
          >
            SCENE & DISTURBANCE
          </button>
          <button
            onClick={() => setActiveTab('pid')}
            className={`flex-1 py-1.5 text-center font-bold transition-colors cursor-pointer ${
              activeTab === 'pid'
                ? 'text-[#00E676] border-b-2 border-[#00E676] bg-[#0C1013]/50'
                : 'text-[#93A0A8] hover:text-[#D9E0E4]'
            }`}
          >
            PID CONTROL
          </button>
        </div>

        {activeTab === 'sim' ? (
          <>
            {/* Group 1: Scene Configuration */}
            <div className="bg-[#0C1013] border border-[#232C33] rounded p-2.5 space-y-3">
              <div className="text-[10px] font-mono font-bold text-[#93A0A8] uppercase tracking-wider flex items-center gap-1.5">
                <Eye size={12} className="text-[#39C5CF]" />
                SCENE CONFIGURATION
              </div>

              {/* Target Speed Slider */}
              <div className="space-y-1">
                <div className="flex justify-between text-[11px] font-mono">
                  <span className="text-[#93A0A8]">TARGET VELOCITY</span>
                  <span className="text-[#00E676] font-bold">{sceneConfig.target_speed_mps} m/s</span>
                </div>
                <input
                  type="range"
                  min="1"
                  max="100"
                  value={sceneConfig.target_speed_mps}
                  onChange={(e) =>
                    onUpdateScene({ ...sceneConfig, target_speed_mps: Number(e.target.value) })
                  }
                  className="w-full accent-[#00E676] cursor-pointer"
                />
              </div>

              {/* Motion Pattern */}
              <div className="space-y-1">
                <label className="text-[10px] font-mono text-[#93A0A8] block">MOTION PATTERN</label>
                <select
                  value={sceneConfig.motion_pattern}
                  onChange={(e) =>
                    onUpdateScene({
                      ...sceneConfig,
                      motion_pattern: e.target.value as SceneConfig['motion_pattern'],
                    })
                  }
                  className="w-full bg-[#11161A] border border-[#232C33] rounded px-2 py-1 text-xs font-mono text-[#D9E0E4] focus:outline-hidden focus:border-[#00E676]"
                >
                  <option value="linear">Linear Trajectory</option>
                  <option value="sinusoidal">Sinusoidal Sweep</option>
                  <option value="lissajous">Lissajous Curve (3:2)</option>
                  <option value="spiral">Spiral Track</option>
                </select>
              </div>

              {/* Distractor Beacons Toggle */}
              <div className="flex items-center justify-between pt-1">
                <span className="text-[11px] font-mono text-[#93A0A8]">DISTRACTOR BEACONS</span>
                <input
                  type="checkbox"
                  checked={sceneConfig.enable_distractors}
                  onChange={(e) =>
                    onUpdateScene({ ...sceneConfig, enable_distractors: e.target.checked })
                  }
                  className="w-4 h-4 accent-[#00E676] rounded cursor-pointer"
                />
              </div>
            </div>

            {/* Group 2: Disturbance Controls */}
            <div className="bg-[#0C1013] border border-[#232C33] rounded p-2.5 space-y-3">
              <div className="text-[10px] font-mono font-bold text-[#93A0A8] uppercase tracking-wider flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <Sparkles size={12} className="text-[#FFB300]" />
                  DISTURBANCE MODELS
                </span>
                <select
                  value={disturbanceConfig.profile}
                  onChange={(e) =>
                    handleProfileChange(e.target.value as DisturbanceConfig['profile'])
                  }
                  className="bg-[#11161A] border border-[#232C33] text-[10px] font-mono rounded px-1.5 py-0.5 text-[#00E676]"
                >
                  <option value="mild">Profile: Mild</option>
                  <option value="moderate">Profile: Moderate</option>
                  <option value="severe">Profile: Severe</option>
                  <option value="custom">Profile: Custom</option>
                </select>
              </div>

              {/* Vibration Jitter */}
              <div className="space-y-1">
                <div className="flex justify-between text-[11px] font-mono">
                  <span className="text-[#93A0A8]">PLATFORM VIBRATION</span>
                  <span className="text-[#D9E0E4] font-bold">{disturbanceConfig.vibration_sigma_urad} μrad</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="50"
                  value={disturbanceConfig.vibration_sigma_urad}
                  onChange={(e) =>
                    onUpdateDisturbance({
                      ...disturbanceConfig,
                      profile: 'custom',
                      vibration_sigma_urad: Number(e.target.value),
                    })
                  }
                  className="w-full accent-[#00E676] cursor-pointer"
                />
              </div>

              {/* Turbulence Index */}
              <div className="space-y-1">
                <div className="flex justify-between text-[11px] font-mono">
                  <span className="text-[#93A0A8]">TURBULENCE INDEX</span>
                  <span className="text-[#D9E0E4] font-bold">{disturbanceConfig.turbulence_index} Cn²</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={disturbanceConfig.turbulence_index}
                  onChange={(e) =>
                    onUpdateDisturbance({
                      ...disturbanceConfig,
                      profile: 'custom',
                      turbulence_index: Number(e.target.value),
                    })
                  }
                  className="w-full accent-[#00E676] cursor-pointer"
                />
              </div>

              {/* Sensor Noise */}
              <div className="space-y-1">
                <div className="flex justify-between text-[11px] font-mono">
                  <span className="text-[#93A0A8]">SENSOR NOISE</span>
                  <span className="text-[#D9E0E4] font-bold">{disturbanceConfig.sensor_noise_sigma} σ px</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="20"
                  value={disturbanceConfig.sensor_noise_sigma}
                  onChange={(e) =>
                    onUpdateDisturbance({
                      ...disturbanceConfig,
                      profile: 'custom',
                      sensor_noise_sigma: Number(e.target.value),
                    })
                  }
                  className="w-full accent-[#00E676] cursor-pointer"
                />
              </div>

              {/* Cloud Occlusion Toggle */}
              <div className="flex items-center justify-between pt-1">
                <span className="text-[11px] font-mono text-[#93A0A8]">CLOUD OCCLUSION (DROPOUT)</span>
                <input
                  type="checkbox"
                  checked={disturbanceConfig.enable_occlusion}
                  onChange={(e) =>
                    onUpdateDisturbance({
                      ...disturbanceConfig,
                      enable_occlusion: e.target.checked,
                    })
                  }
                  className="w-4 h-4 accent-[#00E676] rounded cursor-pointer"
                />
              </div>
            </div>
          </>
        ) : (
          /* PID Controller Configuration */
          <div className="bg-[#0C1013] border border-[#232C33] rounded p-2.5 space-y-3">
            <div className="text-[10px] font-mono font-bold text-[#93A0A8] uppercase tracking-wider flex items-center gap-1.5">
              <Sliders size={12} className="text-[#00E676]" />
              CLOSED-LOOP PID GAINS
            </div>

            <div className="space-y-1">
              <div className="flex justify-between text-[11px] font-mono">
                <span className="text-[#93A0A8]">PROPORTIONAL (Kp)</span>
                <span className="text-[#00E676] font-bold">{pidGains.kp.toFixed(5)}</span>
              </div>
              <input
                type="range"
                min="0.00005"
                max="0.001"
                step="0.00005"
                value={pidGains.kp}
                onChange={(e) => onUpdatePID({ ...pidGains, kp: Number(e.target.value) })}
                className="w-full accent-[#00E676] cursor-pointer"
              />
            </div>

            <div className="space-y-1">
              <div className="flex justify-between text-[11px] font-mono">
                <span className="text-[#93A0A8]">INTEGRAL (Ki)</span>
                <span className="text-[#00E676] font-bold">{pidGains.ki.toFixed(6)}</span>
              </div>
              <input
                type="range"
                min="0"
                max="0.0002"
                step="0.00001"
                value={pidGains.ki}
                onChange={(e) => onUpdatePID({ ...pidGains, ki: Number(e.target.value) })}
                className="w-full accent-[#00E676] cursor-pointer"
              />
            </div>

            <div className="space-y-1">
              <div className="flex justify-between text-[11px] font-mono">
                <span className="text-[#93A0A8]">DERIVATIVE (Kd)</span>
                <span className="text-[#00E676] font-bold">{pidGains.kd.toFixed(6)}</span>
              </div>
              <input
                type="range"
                min="0"
                max="0.0001"
                step="0.000005"
                value={pidGains.kd}
                onChange={(e) => onUpdatePID({ ...pidGains, kd: Number(e.target.value) })}
                className="w-full accent-[#00E676] cursor-pointer"
              />
            </div>

            <div className="space-y-1">
              <div className="flex justify-between text-[11px] font-mono">
                <span className="text-[#93A0A8]">SLEW RATE LIMIT (rad/step)</span>
                <span className="text-[#00E676] font-bold">{pidGains.max_output_step.toFixed(4)}</span>
              </div>
              <input
                type="range"
                min="0.0005"
                max="0.01"
                step="0.0005"
                value={pidGains.max_output_step}
                onChange={(e) =>
                  onUpdatePID({ ...pidGains, max_output_step: Number(e.target.value) })
                }
                className="w-full accent-[#00E676] cursor-pointer"
              />
            </div>

            <p className="text-[10px] text-[#5B6770] font-mono leading-relaxed pt-2 border-t border-[#232C33]">
              Anti-windup clamping and low-pass derivative filter (α=0.25) active. Slew-rate limit enforces physical gimbal inertia.
            </p>
          </div>
        )}
      </div>

      {/* Bottom Modals / Actions */}
      <div className="p-3 border-t border-[#232C33] bg-[#0C1013] space-y-2">
        <button
          onClick={onOpenAnalytics}
          className="w-full py-2 px-3 bg-[#1A2126] hover:bg-[#232C33] border border-[#232C33] rounded font-mono text-xs font-semibold text-[#D9E0E4] flex items-center justify-center gap-2 cursor-pointer transition-colors"
        >
          <BarChart3 size={14} className="text-[#39C5CF]" />
          TELEMETRY LOGS & ANALYTICS
        </button>

        <button
          onClick={onOpenPresentation}
          className="w-full py-2 px-3 bg-[#1A2126] hover:bg-[#232C33] border border-[#232C33] rounded font-mono text-xs font-semibold text-[#D9E0E4] flex items-center justify-center gap-2 cursor-pointer transition-colors"
        >
          <Presentation size={14} className="text-[#00E676]" />
          SIH 26169 PRESENTATION DECK
        </button>
      </div>
    </aside>
  );
};
