# FSOC Coarse-Alignment Virtual Tracking Simulator (SIH 26169)

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![UI-PySide6](https://img.shields.io/badge/GUI-PySide6%20Qt-brightgreen.svg)](https://pypi.org/project/PySide6/)
[![Status-Verified](https://img.shields.io/badge/status-100%25%20Verified-success.svg)](PROJECT_STATUS.md)

A high-fidelity, software-only hardware surrogate designed for Free Space Optical Communication (FSOC) systems. It models a virtual pan-tilt gimbal camera tracking moving optical beacons at 60 Hz under severe realistic environmental disturbances including atmospheric turbulence, platform vibration, sensor noise, cloud occlusion, and camera motion blur.

---

## 📌 Executive Summary & Core Capabilities

- **60 Hz Real-Time Simulation Engine:** Renders synthetic optical beacons with analytical trajectories (Archimedean spiral, linear, sinusoidal, multi-target distractors) and simulated optical camera dynamics.
- **Realistic Environmental Disturbances:** Injects physical turbulence blur, platform jitter/vibration, Gaussian sensor noise, cloud occlusions, and camera motion blur.
- **Robust Computer Vision & Tracking:** Operates a 5-state machine (`SEARCH` ➔ `ACQUIRE` ➔ `TRACK` ➔ `LOST` ➔ `REACQUIRE`) powered by OpenCV spot detection, Kalman filtering, and a lightweight CNN AI patch classifier.
- **Closed-Loop Pan-Tilt Control:** PID controller with anti-windup, derivative filtering, and slew-rate limiting to drive camera centering.
- **Mission-Control Telemetry Cockpit:** PySide6 custom QSS dark-themed interface with rolling charts, status indicators, dynamic parameter controls, and JSON performance log export.
- **External MP4 Video Evaluation:** Headless and GUI evaluation modes for processing external judge benchmark video clips with instant metric reporting (RMSE, Lock Retention Rate, Acquisition Time).
- **Standalone Executable:** Single-folder standalone PyInstaller build requiring no external Python installation (`dist/fsoc_sim/fsoc_sim.exe`).

---

## 🏗️ Architecture Overview

```
+-----------------------------------------------------------------------+
|                             USER INTERFACE                            |
|        PySide6 Dark Cockpit (MainWindow, Rolling Charts, Controls)    |
+-----------------------------------+-----------------------------------+
                                    |
+-----------------------------------v-----------------------------------+
|                            RUNTIME ENGINE                             |
|          LiveTelemetrySource / VideoSource @ 60 Hz Loop (dt=16.67ms)  |
+---------+-------------------------+-------------------------+---------+
          |                         |                         |
+---------v--------+      +---------v--------+      +---------v--------+
|    SIMULATION    |      |   DISTURBANCE    |      |     TRACKING     |
| Scene, Motion,   |=====>| Turbulence, Jitter,|=====>| Detect, Kalman,  |
| Camera Optics    |      | Blur, Occlusion  |      | State Machine, AI|
+------------------+      +------------------+      +--------+---------+
                                                             |
                                                             | TrackResult / Error
+------------------------------------------------------------v----------+
|                            CONTROL LOOP                               |
|        PanTiltPID Controller (Anti-windup & Slew Rate Limit)          |
+-----------------------------------+-----------------------------------+
                                    | Pan/Tilt Camera Command
                                    v
                         (Closes Loop back to Sim)
```

---

## 🛠️ Quick Start & Installation

### Prerequisites
- Python 3.11 or Python 3.12 (64-bit)
- Windows 10/11 or Linux (x86_64)

### 1. Clone & Setup Environment

```powershell
git clone https://github.com/mustafasidd05-collab/SIH-FSOC.git
cd SIH-FSOC

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1   # On Windows
# source venv/bin/activate    # On Linux/macOS

# Install dependencies
pip install -r requirements.txt
```

### 2. Launch Interactive 60 Hz Cockpit

```powershell
python -m ui.main_window
```

### 3. Evaluate External MP4 Video Clips

```powershell
# Interactive GUI tracking on custom video
python -m ui.main_window --video "path/to/benchmark_clip.mp4"

# Headless evaluation with JSON performance log export
python evaluate_video.py --video "path/to/benchmark_clip.mp4" --output "eval_results.json"
```

### 4. Run Offscreen Self-Test & Screenshots

```powershell
python -m ui.main_window --selftest
```

---

## 🧪 Testing & Verification

Run the full automated unit and integration test suite:

```powershell
pytest
```

---

## 📦 Building Standalone Executable

To build the PyInstaller standalone executable package:

```powershell
pyinstaller build/build_executable.spec
```

The executable will be generated at `dist/fsoc_sim/fsoc_sim.exe`.

---

## 📖 Deliverables & Documentation

- 📄 [**User Manual**](USER_MANUAL.md) — Comprehensive operational guide for engineers and judges.
- 📄 [**Technical Report**](TECHNICAL_REPORT.md) — In-depth architectural breakdown, math formulations, and design rationale.
- 📊 [**Project Status**](PROJECT_STATUS.md) — Live module status matrix and verification metrics.
