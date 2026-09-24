# USER MANUAL — FSOC Coarse-Alignment Virtual Tracking Simulator (SIH 26169)

> **Version:** 1.0.0  
> **Target Audience:** FSOC Engineers, System Evaluators, and Challenge Judges  
> **Executable Name:** `fsoc_sim.exe` (or `python -m ui.main_window`)

---

## 1. Executive Overview & System Requirements

The **FSOC Coarse-Alignment Virtual Tracking Simulator** is a high-fidelity, software-only hardware surrogate designed for Free Space Optical Communication (FSOC) systems. It models a virtual pan-tilt gimbal camera tracking moving optical beacons at 60 Hz under severe realistic environmental disturbances including atmospheric turbulence, platform vibration, sensor noise, cloud occlusion, and camera motion blur.

### 1.1 Minimum System Requirements

- **Operating System:** Windows 10/11 (64-bit) or Linux (x86_64)
- **Processor:** Dual-Core 2.0 GHz CPU or better
- **System RAM:** 4 GB minimum (8 GB recommended)
- **Display Resolution:** 1440 × 900 minimum recommended (full scroll support for 1080p displays)
- **Python Runtime (Development mode):** Python 3.11+ with PySide6, OpenCV, NumPy, SciPy, filterpy

---

## 2. Launch & Execution Modes

The application can be launched in multiple flexible operational modes via the command line interface or standalone executable:

```powershell
# Mode 1: Interactive GUI with 60 Hz Synthetic Virtual Scene (Default)
.\fsoc_sim.exe --live

# Mode 2: Interactive GUI with External Judge Benchmark Video (.mp4)
.\fsoc_sim.exe --video "path\to\benchmark_clip.mp4"

# Mode 3: Headless Offscreen Verification & Screenshot Audit
.\fsoc_sim.exe --selftest

# Mode 4: Headless Video Evaluator Script (Export JSON report directly)
python evaluate_video.py --video "path\to\benchmark_clip.mp4" --output "eval_results.json"
```

---

## 3. Mission-Control Cockpit UI Layout

The interface uses a custom Dark Mission-Control design system adhering to strict color hierarchy, high-contrast monospace typography, and zero vertical clipping.

```
+-----------------------------------------------------------------------------------+
|  [ FSOC COARSE-ALIGNMENT SIMULATOR ]   [ VIRTUAL SCENE (60 Hz) ]    [ EXPORT LOG ] |
+-----------------------------------------------------------------------------------+
|  [ LOCK STATE INDICATOR: SEARCH / ACQUIRE / TRACK / LOST / REACQUIRE ]            |
+------------------------------------+----------------------------------------------+
|                                    |  CONFIG PANEL (Scrollable)                   |
|                                    |  ------------------------                    |
|  VIDEO PANE                        |  Target Speed (1–100 m/s)                    |
|  - Boresight reticle (Crosshair)   |  Target Blob Radius (2–30 px)                 |
|  - Centroid Bounding Box           |  Motion Pattern:                             |
|  - Tracking Error Vector (Dashed)  |    - Linear Track / Sinusoidal Sweep         |
|  - HUD Telemetry (FPS, Error, State|    - Lissajous Curve / Archimedean Spiral    |
|                                    |  [ DEPLOY FAULT DECOY ] (Distractor Beacon)   |
|                                    |  Disturbance Preset: Mild/Moderate/Severe    |
|                                    |  Platform Vibration (0–5.0 px σ)              |
|                                    |  Atmospheric Turbulence (0–5.0 px σ)         |
|                                    |  Sensor Noise (6–40 dB SNR)                  |
|                                    |  PID Gain Tuning (Kp, Ki, Kd, Max Step)      |
|                                    |  [ RESET INTEGRAL / PID ]                    |
|                                    |  [ SWITCH TO VIRTUAL SCENE ]                 |
+------------------------------------+----------------------------------------------+
|  ROLLING ANALYTICS CHARTS (FPS, Tracking RMSE, Lock Retention Rate)               |
+-----------------------------------------------------------------------------------+
|  TELEMETRY STRIP (Frame ID, Time, Az/El Error, Lock Fraction, Acquisition Time)   |
+-----------------------------------------------------------------------------------+
```

---

## 4. Interactive Control Guide

### 4.1 Motion Trajectory Patterns

Select from four realistic target flight trajectories:
1. **Linear Track:** Constant velocity continuous sweep across the operational field of view.
2. **Sinusoidal Sweep:** Smooth horizontal and vertical angular oscillation simulating satellite pass sweeps.
3. **Lissajous Curve:** Dual-axis figure-8 trajectory with a 1:2 frequency ratio.
4. **Archimedean Spiral:** Outward expanding spiral sweep testing tracker performance under acceleration.

### 4.2 Distractor & Fault Injection

- **Deploy Fault Decoy Button:** Toggles the injection of a secondary, dimmer distractor beacon into the optical scene. The classical CV and Kalman filter pipeline tests target identity maintenance without switching locks.

### 4.3 Disturbance Regimes

Choose from three calibrated preset regimes or adjust individual sliders:
- **Mild:** $\sigma_{\text{vib}} = 0.4$ px, $\sigma_{\text{turb}} = 0.4$ px, $\text{SNR} = 35$ dB
- **Moderate:** $\sigma_{\text{vib}} = 1.2$ px, $\sigma_{\text{turb}} = 1.5$ px, $\text{SNR} = 22$ dB
- **Severe:** $\sigma_{\text{vib}} = 3.0$ px, $\sigma_{\text{turb}} = 3.5$ px, $\text{SNR} = 12$ dB

### 4.4 PID Controller Gain Tuning

Fine-tune closed-loop pan-tilt control gains in real-time:
- **Kp (Proportional Gain):** Primary correction strength ($0.0001 - 0.0050$ rad/px).
- **Ki (Integral Gain):** Accumulator for steady-state error cancellation ($0.00000 - 0.00050$).
- **Kd (Derivative Gain):** Low-pass filtered damping term to minimize overshoot ($0.00000 - 0.00050$).
- **Max Slew Step:** Maximum commanded angular delta per step ($0.001 - 0.010$ rad/step).
- **Reset Integral:** Instantly resets accumulated PID integral error back to zero.

---

## 5. Performance Log Export

Click **`EXPORT LOG`** on the top header bar to save complete run telemetry to a JSON report. The exported log contains:
- Total frames evaluated and elapsed simulation time.
- Time-to-acquisition ($t_{\text{acq}}$) in seconds.
- Overall lock retention rate (%).
- Root-Mean-Square Tracking Error ($\text{RMSE}_{\text{px}}$ and $\text{RMSE}_{\text{mrad}}$).
- Full frame-by-frame telemetry arrays.
