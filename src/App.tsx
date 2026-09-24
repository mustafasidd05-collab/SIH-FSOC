import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  CameraState,
  DisturbanceConfig,
  SceneConfig,
  PIDGains,
  SimFrame,
  TelemetryPacket,
  TrackState,
  TrackResult,
} from './types/contracts';
import { Scene } from './sim/scene';
import { DisturbancePipeline } from './disturbance/pipeline';
import { SceneRenderer } from './sim/render';
import { TrackPipeline } from './tracking/pipeline';
import { ControlLoop } from './control/loop';
import { PerformanceLogger } from './telemetry/performanceLogger';
import { drawHudOverlay } from './sim/hudOverlay';

import { LockStateIndicator } from './components/LockStateIndicator';
import { VideoCanvas } from './components/VideoCanvas';
import { RollingChart } from './components/RollingChart';
import { TelemetryStrip } from './components/TelemetryStrip';
import { ConfigSidebar } from './components/ConfigSidebar';
import { AnalyticsModal } from './components/AnalyticsModal';
import { PresentationModal } from './components/PresentationModal';

// Default initial camera matching contracts
const INITIAL_CAMERA: CameraState = {
  pan_rad: 0.0,
  tilt_rad: 0.0,
  pan_min_rad: -Math.PI / 2, // -90 deg
  pan_max_rad: Math.PI / 2,  // +90 deg
  tilt_min_rad: -Math.PI / 2,
  tilt_max_rad: Math.PI / 2,
  fov_h_rad: 0.069813, // 4.0 deg in radians
  fov_v_rad: 0.052360, // 3.0 deg in radians
  width_px: 640,
  height_px: 480,
};

const INITIAL_SCENE_CONFIG: SceneConfig = {
  target_speed_mps: 15.0,
  motion_pattern: 'sinusoidal',
  enable_distractors: false,
};

const INITIAL_DISTURBANCE_CONFIG: DisturbanceConfig = {
  profile: 'mild',
  enable_turbulence: true,
  enable_vibration: true,
  enable_sensor_noise: true,
  enable_occlusion: false,
  enable_motion_blur: false,
  vibration_sigma_urad: 4,
  turbulence_index: 10,
  sensor_noise_sigma: 1,
};

const INITIAL_PID_GAINS: PIDGains = {
  kp: 0.0003,
  ki: 0.00005,
  kd: 0.00002,
  max_output_step: 0.003,
};

export const App: React.FC = () => {
  // Config state
  const [sceneConfig, setSceneConfig] = useState<SceneConfig>(INITIAL_SCENE_CONFIG);
  const [distConfig, setDistConfig] = useState<DisturbanceConfig>(INITIAL_DISTURBANCE_CONFIG);
  const [pidGains, setPidGains] = useState<PIDGains>(INITIAL_PID_GAINS);
  const [isRunning, setIsRunning] = useState<boolean>(true);

  // Modals state
  const [isAnalyticsOpen, setIsAnalyticsOpen] = useState<boolean>(false);
  const [isPresentationOpen, setIsPresentationOpen] = useState<boolean>(false);

  // Current simulation states
  const [camera, setCamera] = useState<CameraState>(INITIAL_CAMERA);
  const [currentPacket, setCurrentPacket] = useState<TelemetryPacket | null>(null);
  const [trackResult, setTrackResult] = useState<TrackResult | null>(null);

  // Chart telemetry rolling states
  const [chartFps, setChartFps] = useState<number>(60);
  const [chartErrorPx, setChartErrorPx] = useState<number>(0);
  const [chartLockFraction, setChartLockFraction] = useState<number>(100);
  const [chartGimbalAngle, setChartGimbalAngle] = useState<number>(0);
  const [chartTimestamp, setChartTimestamp] = useState<number>(0);

  // Engine instance refs
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const sceneRef = useRef<Scene>(new Scene(INITIAL_SCENE_CONFIG));
  const distPipelineRef = useRef<DisturbancePipeline>(new DisturbancePipeline(INITIAL_DISTURBANCE_CONFIG));
  const rendererRef = useRef<SceneRenderer>(new SceneRenderer());
  const trackPipelineRef = useRef<TrackPipeline>(new TrackPipeline());
  const controlLoopRef = useRef<ControlLoop>(new ControlLoop(INITIAL_PID_GAINS));
  const loggerRef = useRef<PerformanceLogger>(new PerformanceLogger());

  // Simulation timing refs
  const simTimeRef = useRef<number>(0);
  const frameIdRef = useRef<number>(0);
  const lastTimeRef = useRef<number | null>(null);
  const fpsWindowRef = useRef<number[]>([]);
  const animFrameIdRef = useRef<number | null>(null);

  // Sync config changes with instances
  useEffect(() => {
    sceneRef.current.updateConfig(sceneConfig);
  }, [sceneConfig]);

  useEffect(() => {
    distPipelineRef.current.updateConfig(distConfig);
  }, [distConfig]);

  useEffect(() => {
    controlLoopRef.current.setGains(pidGains);
  }, [pidGains]);

  const handleReset = useCallback(() => {
    simTimeRef.current = 0;
    frameIdRef.current = 0;
    lastTimeRef.current = null;
    fpsWindowRef.current = [];
    trackPipelineRef.current.reset();
    controlLoopRef.current.reset();
    loggerRef.current.reset();
    setCamera(INITIAL_CAMERA);
    setTrackResult(null);
    setCurrentPacket(null);
  }, []);

  const handleSelectTarget = useCallback((px: number, py: number) => {
    trackPipelineRef.current.selectTarget([px, py]);
  }, []);

  // Main 60 FPS simulation loop
  useEffect(() => {
    if (!isRunning) return;

    const loop = (timestampMs: number) => {
      if (lastTimeRef.current === null) {
        lastTimeRef.current = timestampMs;
      }
      const dt = Math.max(0.001, Math.min(0.05, (timestampMs - lastTimeRef.current) / 1000.0));
      lastTimeRef.current = timestampMs;
      simTimeRef.current += dt;
      frameIdRef.current += 1;

      const t = simTimeRef.current;
      const frameId = frameIdRef.current;

      // Calculate instantaneous FPS
      const currentFps = dt > 0 ? 1.0 / dt : 60.0;
      fpsWindowRef.current.push(currentFps);
      if (fpsWindowRef.current.length > 30) fpsWindowRef.current.shift();
      const avgFps =
        fpsWindowRef.current.reduce((a, b) => a + b, 0) / fpsWindowRef.current.length;

      // 1. Get analytical target positions
      const targets = sceneRef.current.getTargets(t);

      // 2. Render target scene & disturbances to canvas context
      const canvas = canvasRef.current;
      let projectedTargets: Array<{ targetId: number; px: number; py: number; visible: boolean; role?: string }> = [];
      let simFrameImage: ImageData | null = null;

      if (canvas) {
        const ctx = canvas.getContext('2d', { willReadFrequently: true });
        if (ctx) {
          // Render background, PSF blobs, sensor noise, jitter
          const renderOut = rendererRef.current.renderToCanvas(
            ctx,
            targets,
            camera,
            t,
            dt,
            distPipelineRef.current
          );
          projectedTargets = renderOut.targetPixelCoords;

          try {
            simFrameImage = ctx.getImageData(0, 0, camera.width_px, camera.height_px);
          } catch {
            simFrameImage = null;
          }

          // 3. Process Computer Vision Tracking Pipeline
          const simFrame: SimFrame = {
            frame_id: frameId,
            timestamp_s: t,
            image: simFrameImage,
            camera,
          };

          const result = trackPipelineRef.current.process(simFrame, projectedTargets);

          // 4. Closed-Loop Pan-Tilt Control Step
          const { camera: nextCamera } = controlLoopRef.current.step(result, camera, dt);

          // 5. Draw Mission-Control HUD Overlays (reticle, target marker, bounding box, error vector)
          drawHudOverlay(ctx, camera.width_px, camera.height_px, result);

          // 6. Calculate Telemetry & Log Packet
          const lockFraction = loggerRef.current.getLockRetentionRate(120);
          const acqTime = loggerRef.current.getAcquisitionTime();

          const errorAzRad = !isNaN(result.error_px[0])
            ? (result.error_px[0] / camera.width_px) * camera.fov_h_rad
            : NaN;
          const errorElRad = !isNaN(result.error_px[1])
            ? (result.error_px[1] / camera.height_px) * camera.fov_v_rad
            : NaN;

          const packet: TelemetryPacket = {
            frame_id: frameId,
            timestamp_s: t,
            fps: avgFps,
            track_state: result.state,
            error_px: result.error_px,
            error_az_rad: isNaN(errorAzRad) ? 0 : errorAzRad,
            error_el_rad: isNaN(errorElRad) ? 0 : errorElRad,
            lock_fraction: lockFraction,
            acquisition_time_s: acqTime,
            loop_time_s: dt,
          };

          loggerRef.current.logPacket(packet);

          // Update React states for UI rendering
          setCamera(nextCamera);
          setTrackResult(result);
          setCurrentPacket(packet);

          // Chart updates
          setChartFps(avgFps);
          setChartErrorPx(
            !isNaN(result.error_px[0]) && !isNaN(result.error_px[1])
              ? Math.hypot(result.error_px[0], result.error_px[1])
              : 0
          );
          setChartLockFraction(lockFraction * 100);
          setChartGimbalAngle(Math.hypot(nextCamera.pan_rad, nextCamera.tilt_rad) * (180 / Math.PI));
          setChartTimestamp(t);
        }
      }

      animFrameIdRef.current = requestAnimationFrame(loop);
    };

    animFrameIdRef.current = requestAnimationFrame(loop);

    return () => {
      if (animFrameIdRef.current !== null) {
        cancelAnimationFrame(animFrameIdRef.current);
      }
    };
  }, [isRunning, camera]);

  const activeTrackState = trackResult?.state ?? TrackState.SEARCH;

  return (
    <div className="w-screen h-screen bg-[#0A0D0F] text-[#D9E0E4] flex flex-col overflow-hidden font-sans select-none">
      {/* Top Application Bar */}
      <header className="h-12 bg-[#11161A] border-b border-[#232C33] px-4 flex items-center justify-between z-20">
        <div className="flex items-center gap-3">
          <div className="w-3 h-3 rounded-full bg-[#00E676] animate-pulse" />
          <h1 className="text-xs font-mono font-bold tracking-wider text-[#D9E0E4] uppercase">
            FSOC VIRTUAL TRACKING SIMULATOR <span className="text-[#5B6770]">|</span>{' '}
            <span className="text-[#93A0A8]">SIH 26169 COARSE-ALIGNMENT</span>
          </h1>
        </div>

        <div className="flex items-center gap-4 text-xs font-mono">
          <div className="hidden sm:flex items-center gap-2 bg-[#0C1013] border border-[#232C33] px-3 py-1 rounded text-[#93A0A8]">
            <span>OPTICAL LINK:</span>
            <span className="text-[#00E676] font-bold">1000m BEACON</span>
          </div>

          <button
            onClick={() => setIsPresentationOpen(true)}
            className="px-3 py-1 bg-[#1A2126] hover:bg-[#232C33] border border-[#232C33] rounded font-mono text-xs text-[#00E676] font-semibold cursor-pointer transition-colors"
          >
            SLIDES
          </button>

          <button
            onClick={() => setIsAnalyticsOpen(true)}
            className="px-3 py-1 bg-[#1A2126] hover:bg-[#232C33] border border-[#232C33] rounded font-mono text-xs text-[#39C5CF] font-semibold cursor-pointer transition-colors"
          >
            ANALYTICS
          </button>
        </div>
      </header>

      {/* Main Cockpit Layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Configuration & Controls Sidebar */}
        <ConfigSidebar
          isRunning={isRunning}
          onToggleRun={() => setIsRunning((prev) => !prev)}
          onReset={handleReset}
          sceneConfig={sceneConfig}
          onUpdateScene={setSceneConfig}
          disturbanceConfig={distConfig}
          onUpdateDisturbance={setDistConfig}
          pidGains={pidGains}
          onUpdatePID={setPidGains}
          onOpenAnalytics={() => setIsAnalyticsOpen(true)}
          onOpenPresentation={() => setIsPresentationOpen(true)}
        />

        {/* Center: Live Video Feed with HUD Overlay */}
        <main className="flex-1 h-full p-2.5 flex flex-col min-w-0 bg-[#0A0D0F]">
          <div className="flex-1 w-full h-full relative rounded overflow-hidden">
            <VideoCanvas
              canvasRef={canvasRef}
              camera={camera}
              packet={currentPacket}
              onSelectTarget={handleSelectTarget}
            />
          </div>
        </main>

        {/* Right Cockpit Panel: Lock State Indicator + Telemetry Charts */}
        <aside
          id="telemetryChartsPanel"
          className="w-[260px] h-full bg-[#11161A] border-l border-[#232C33] p-3 flex flex-col gap-3 justify-between overflow-y-auto select-none"
        >
          {/* Top: 230px LockStateIndicator Banner */}
          <div className="flex justify-center">
            <LockStateIndicator state={activeTrackState} />
          </div>

          {/* Middle: 4 Rolling Real-Time Telemetry Charts */}
          <div className="flex-1 flex flex-col gap-2 justify-center">
            <RollingChart
              id="chart-fps"
              title="SIMULATION FPS"
              value={chartFps}
              timestamp={chartTimestamp}
              minVal={0}
              maxVal={80}
              unit=""
              lineColorHex="#00E676"
            />

            <RollingChart
              id="chart-tracking-error"
              title="TRACKING ERROR (PX)"
              value={chartErrorPx}
              timestamp={chartTimestamp}
              minVal={0}
              maxVal={30}
              unit="px"
              lineColorHex="#FFB300"
            />

            <RollingChart
              id="chart-lock-fraction"
              title="LOCK RETENTION"
              value={chartLockFraction}
              timestamp={chartTimestamp}
              minVal={0}
              maxVal={100}
              unit="%"
              lineColorHex="#39C5CF"
            />

            <RollingChart
              id="chart-gimbal-offset"
              title="GIMBAL DEFLECTION"
              value={chartGimbalAngle}
              timestamp={chartTimestamp}
              minVal={0}
              maxVal={5}
              unit="°"
              lineColorHex="#B57CFF"
            />
          </div>

          {/* Bottom Cockpit Status */}
          <div className="bg-[#0C1013] border border-[#232C33] p-2 rounded text-[10px] font-mono space-y-1">
            <div className="flex justify-between text-[#93A0A8]">
              <span>KALMAN FILTER</span>
              <span className="text-[#00E676] font-bold">CONSTANT VELOCITY</span>
            </div>
            <div className="flex justify-between text-[#93A0A8]">
              <span>SPATIAL GATE</span>
              <span className="text-[#D9E0E4]">80 px RADIUS</span>
            </div>
            <div className="flex justify-between text-[#93A0A8]">
              <span>CONTROL GATING</span>
              <span className="text-[#00E676]">TRACK / REACQUIRE</span>
            </div>
          </div>
        </aside>
      </div>

      {/* Bottom Telemetry Strip */}
      <TelemetryStrip packet={currentPacket} />

      {/* Analytics & Performance Modal */}
      <AnalyticsModal
        isOpen={isAnalyticsOpen}
        onClose={() => setIsAnalyticsOpen(false)}
        logger={loggerRef.current}
      />

      {/* Presentation Deck Modal */}
      <PresentationModal
        isOpen={isPresentationOpen}
        onClose={() => setIsPresentationOpen(false)}
      />
    </div>
  );
};
