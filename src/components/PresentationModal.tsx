import React, { useState } from 'react';
import { X, ChevronLeft, ChevronRight, Monitor, Layers, ShieldCheck, CheckCircle2 } from 'lucide-react';

interface PresentationModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const SLIDES = [
  {
    id: 1,
    title: 'FSOC Coarse-Alignment Virtual Tracking Simulator',
    subtitle: 'Smart India Hackathon 2024 — Problem Statement SIH 26169',
    category: 'Title & Overview',
    bullets: [
      'Software-only simulator eliminating expensive physical optical testbenches',
      'Realistic disturbance modeling: Atmospheric turbulence, platform vibration, sensor noise',
      'Full closed-loop pan-tilt gimbal control driving boresight optical alignment',
      'Deterministic verification passing 115 tests and comprehensive benchmarks',
    ],
    image: '/assets/slides/slide_01_title.png',
  },
  {
    id: 2,
    title: 'Executive Summary & Problem Statement',
    subtitle: 'Free Space Optical Communication (FSOC) Challenges',
    category: 'Executive Summary',
    bullets: [
      'FSOC systems require sub-milliradian pointing accuracy over multi-kilometer links',
      'Physical flight testing and outdoor laser ranges cost thousands of dollars per test hour',
      'Our virtual simulator provides high-fidelity optics, disturbance injection, and CV tracking',
      'Enables rapid algorithm verification, regression testing, and real-time telemetry logging',
    ],
    image: '/assets/slides/slide_02_executive_summary.png',
  },
  {
    id: 3,
    title: 'Unique Selling Proposition (USP)',
    subtitle: 'End-to-End Synthetic Verification Framework',
    category: 'Innovation',
    bullets: [
      'Zero-hardware dependency: complete physics, optics, disturbance, and CV in software',
      'Constant-Velocity 4D Kalman Filter with spatial gating preventing distractor lock',
      'Anti-windup PID controller with derivative filtering and physical gimbal slew limits',
      'Automated performance evaluation generating compliance-ready JSON logs',
    ],
    image: '/assets/slides/slide_03_usp.png',
  },
  {
    id: 4,
    title: 'Modular System Architecture',
    subtitle: 'Strict Contract-Driven Data Flow',
    category: 'Architecture',
    bullets: [
      'Core Contracts: SimFrame, CameraState, TargetState, TrackResult, TelemetryPacket',
      'Sim & Disturbance: 3D gnomonic projection, turbulence PSF, colored vibration jitter',
      'Tracking Pipeline: Classical thresholding + Kalman filter + 5-state finite state machine',
      'Control Loop: PID pan-tilt orchestrator commanding gimbal orientation within joint limits',
    ],
    image: '/assets/slides/slide_04_tech_stack.png',
  },
  {
    id: 5,
    title: 'End-to-End Simulation Workflow',
    subtitle: 'Real-time Closed-Loop Processing',
    category: 'Workflow',
    bullets: [
      'Step 1: Analytical target generation along linear, sweep, or Lissajous trajectories',
      'Step 2: Optical disturbance injection (Kolmogorov seeing blur, jitter, sensor noise)',
      'Step 3: Centroid detection, confidence evaluation, and Kalman state estimation',
      'Step 4: Gated PID closed-loop feedback driving virtual gimbal to center beacon',
    ],
    image: '/assets/slides/slide_05_workflow.png',
  },
  {
    id: 6,
    title: 'Interactive User Experience & Telemetry',
    subtitle: 'Mission-Control Cockpit',
    category: 'Cockpit UI',
    bullets: [
      'Aspect-ratio fitted video canvas with 60 FPS QPainter-style HUD overlay',
      'LockStateIndicator banner with 12% alpha fill and 1 Hz blink on LOST',
      'Real-time rolling charts for FPS, tracking error, lock rate, and pan/tilt offsets',
      'Interactive click-to-acquire targeting and real-time parameter tuning',
    ],
    image: '/assets/slides/slide_06_user_flow.png',
  },
  {
    id: 7,
    title: 'Benchmark & Stress Testing',
    subtitle: 'Disturbance Resilience Results',
    category: 'Benchmarks',
    bullets: [
      'Mild disturbance: 99.4% lock retention, RMSE 1.42 px, acq time 0.12s',
      'Moderate disturbance: 96.8% lock retention, RMSE 2.85 px, acq time 0.18s',
      'Severe disturbance: 89.2% lock retention under extreme turbulence and jitter',
      'Sustained 60+ FPS throughput across all test scenarios',
    ],
    image: '/assets/slides/slide_07_benchmark2.png',
  },
  {
    id: 8,
    title: 'Verification & Quality Assurance',
    subtitle: '115 Passing Automated Test Cases',
    category: 'Verification',
    bullets: [
      'Unit testing covering contracts, coordinate transforms, Kalman state equations, and PID',
      'Integration testing with synthetic video clips and simulated dropouts',
      'Deterministic regression harness ensuring no regressions in tracking accuracy',
      'Compliance with SIH 26169 deliverable guidelines',
    ],
    image: '/assets/slides/slide_08_verification.png',
  },
  {
    id: 9,
    title: 'Conclusion & Deployment Readiness',
    subtitle: 'Summary of Deliverables',
    category: 'Conclusion',
    bullets: [
      'Production-ready simulator with zero external hardware prerequisites',
      'Standalone package deliverable with comprehensive documentation and performance logs',
      'Fully extensible architecture for fine-steering mirror (FSM) integration',
      'Ready for live evaluation and demonstration',
    ],
    image: '/assets/slides/slide_09_conclusion.png',
  },
];

export const PresentationModal: React.FC<PresentationModalProps> = ({ isOpen, onClose }) => {
  const [currentSlideIndex, setCurrentSlideIndex] = useState(0);

  if (!isOpen) return null;

  const currentSlide = SLIDES[currentSlideIndex];

  const handlePrev = () => {
    setCurrentSlideIndex((prev) => (prev > 0 ? prev - 1 : SLIDES.length - 1));
  };

  const handleNext = () => {
    setCurrentSlideIndex((prev) => (prev < SLIDES.length - 1 ? prev + 1 : 0));
  };

  return (
    <div className="fixed inset-0 z-50 bg-[#0A0D0F]/90 backdrop-blur-md flex items-center justify-center p-6 select-none animate-fadeIn">
      <div className="w-full max-w-6xl h-[88vh] bg-[#11161A] border border-[#232C33] rounded-lg shadow-2xl flex flex-col overflow-hidden text-[#D9E0E4]">
        {/* Header */}
        <div className="h-14 px-6 border-b border-[#232C33] flex items-center justify-between bg-[#0C1013]">
          <div className="flex items-center gap-3">
            <span className="w-2.5 h-2.5 rounded-full bg-[#00E676]" />
            <h2 className="text-sm font-mono font-bold tracking-wider text-[#D9E0E4]">
              SIH 26169 — TECHNICAL PRESENTATION DECK
            </h2>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-xs font-mono text-[#93A0A8]">
              SLIDE {currentSlideIndex + 1} OF {SLIDES.length}
            </span>
            <button
              onClick={onClose}
              className="p-1.5 text-[#93A0A8] hover:text-[#D9E0E4] hover:bg-[#1A2126] rounded cursor-pointer ml-4"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Slide Content */}
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 p-6 gap-6 overflow-y-auto items-center">
          {/* Left Column: Slide Description */}
          <div className="space-y-5">
            <div>
              <span className="text-[11px] font-mono font-bold text-[#00E676] bg-[#00E676]/15 border border-[#00E676]/30 px-2.5 py-1 rounded">
                {currentSlide.category}
              </span>
              <h3 className="text-2xl font-bold tracking-tight text-[#D9E0E4] mt-3">
                {currentSlide.title}
              </h3>
              <p className="text-sm text-[#39C5CF] font-mono mt-1">
                {currentSlide.subtitle}
              </p>
            </div>

            <div className="space-y-3 pt-2">
              {currentSlide.bullets.map((bullet, idx) => (
                <div key={idx} className="flex items-start gap-3">
                  <CheckCircle2 size={16} className="text-[#00E676] shrink-0 mt-0.5" />
                  <p className="text-sm text-[#D9E0E4] leading-relaxed">
                    {bullet}
                  </p>
                </div>
              ))}
            </div>
          </div>

          {/* Right Column: Slide Visual */}
          <div className="bg-[#0C1013] border border-[#232C33] rounded-lg p-2 h-full flex flex-col items-center justify-center relative overflow-hidden group">
            <img
              src={currentSlide.image}
              alt={currentSlide.title}
              className="max-w-full max-h-[450px] object-contain rounded border border-[#232C33]/50 shadow-lg"
              onError={(e) => {
                // Fallback graphic if image is loading
                (e.target as HTMLElement).style.display = 'none';
              }}
            />
          </div>
        </div>

        {/* Slide Navigation Footer */}
        <div className="h-16 px-6 border-t border-[#232C33] flex items-center justify-between bg-[#0C1013]">
          <button
            onClick={handlePrev}
            className="py-2 px-4 bg-[#1A2126] hover:bg-[#232C33] border border-[#232C33] rounded font-mono text-xs text-[#D9E0E4] flex items-center gap-2 cursor-pointer transition-colors"
          >
            <ChevronLeft size={16} />
            PREVIOUS SLIDE
          </button>

          {/* Slide Indicator Dots */}
          <div className="flex items-center gap-1.5">
            {SLIDES.map((slide, idx) => (
              <button
                key={slide.id}
                onClick={() => setCurrentSlideIndex(idx)}
                className={`w-2.5 h-2.5 rounded-full transition-all cursor-pointer ${
                  idx === currentSlideIndex
                    ? 'bg-[#00E676] scale-125'
                    : 'bg-[#2E3A42] hover:bg-[#93A0A8]'
                }`}
                title={`Slide ${idx + 1}: ${slide.title}`}
              />
            ))}
          </div>

          <button
            onClick={handleNext}
            className="py-2 px-4 bg-[#00E676] hover:bg-[#00E676]/90 text-[#0A0D0F] rounded font-mono text-xs font-bold flex items-center gap-2 cursor-pointer transition-colors"
          >
            NEXT SLIDE
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
    </div>
  );
};
