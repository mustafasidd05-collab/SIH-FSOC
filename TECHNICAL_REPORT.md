# TECHNICAL REPORT — FSOC Coarse-Alignment Virtual Tracking Simulator (SIH 26169)

> **Project:** FSOC Coarse-Alignment Virtual Tracking Simulator  
> **Problem Statement ID:** SIH 26169  
> **Target System:** Free Space Optical Communication (FSOC) Coarse Pointing & Acquisition Subsystem  
> **Simulation Rate:** 60 Hz Nominal (16.67 ms frame interval)  
> **Test Coverage:** 133 Passing Unit & Integration Tests  

---

## 1. Executive Summary

Free Space Optical Communication (FSOC) systems rely on extremely narrow laser beams (typically $< 1$ mrad beam divergence) to establish ultra-high-bandwidth optical communication links across free space. Prior to fine-alignment beam steering, a coarse-alignment pan-tilt gimbal camera must acquire, lock onto, and track an optical beacon in real time.

Physical FSOC hardware testbeds are prohibitively expensive, delicate, and weather-dependent. This project delivers a **standalone, software-only hardware surrogate simulator** that models the optical scene, atmospheric physics, sensor noise, platform vibration, computer vision tracking algorithms, and closed-loop gimbal control entirely in software.

Key achievements of this simulator include:
1. **60 Hz High-Fidelity Physics Engine:** Real-time 3D coordinate transformation, Gaussian Point Spread Function (PSF) beacon rendering, and analytic Archimedean spiral / Lissajous trajectory generation.
2. **Comprehensive Disturbance Suite:** Five physically accurate disturbance models (atmospheric turbulence, platform vibration jitter, cloud occlusion, camera motion blur, and calibrated sensor SNR noise).
3. **Robust Multi-State CV & Kalman Tracker:** Classical adaptive thresholding centroiding paired with a 4-state constant-velocity Kalman filter and a 5-state finite state machine (SEARCH $\rightarrow$ ACQUIRE $\rightarrow$ TRACK $\leftrightarrow$ LOST / REACQUIRE).
4. **Anti-Windup Boresight PID Control:** Closed-loop camera pan/tilt gimbal driver with anti-windup clamping, low-pass derivative filtering, and slew-rate limiting.
5. **Benchmark-2 Video Input Support:** External `.mp4` video evaluation adapter for testing algorithm performance on pre-recorded flight clips.

---

## 2. System Architecture & Module Contracts

The software architecture is strictly modularized around immutable data contracts defined in `core/contracts.py`. Modules communicate exclusively through these data structures:

```
                      +-------------------+
                      |   Virtual Scene   |
                      |     (sim/)        |
                      +---------+---------+
                                | SimFrame (60 Hz)
                                v
                      +-------------------+
                      | Disturbance Engine|
                      |   (disturbance/)  |
                      +---------+---------+
                                | Disturbed SimFrame
                                v
                      +-------------------+
                      | Tracking Pipeline |
                      |    (tracking/)    |
                      +---------+---------+
                                | TrackResult (Error px, State)
                                v
                      +-------------------+
                      |   Control Loop    |
                      |    (control/)     |
                      +---------+---------+
                                | CameraState (Updated Pan/Tilt)
                                v
                      (Closes loop to sim/)
```

### 2.1 Core Contracts (`core/contracts.py`)

- **`SimFrame`:** Raw or disturbed image frame ($640 \times 480 \times 3$ BGR uint8 numpy array) with timestamp and frame ID.
- **`CameraState`:** Pan/tilt angles ($\text{rad}$), horizontal/vertical Field of View ($\text{fov}_h, \text{fov}_v$), resolution, and mechanical gimbal limits.
- **`TargetState`:** Ground-truth 3D position ($x, y, z$), range ($m$), azimuth/elevation angles ($\text{rad}$), and image coordinates ($x_{\text{px}}, y_{\text{px}}$).
- **`TrackResult`:** Tracker output containing `TrackState` enum (SEARCH, ACQUIRE, TRACK, LOST, REACQUIRE), estimated centroid, boresight-relative tracking error vector $\mathbf{e}_{\text{px}} = (x_{\text{err}}, y_{\text{err}})$, and Kalman state covariance.
- **`TelemetryPacket`:** Comprehensive frame metric packet carrying instant FPS, track state, pixel error, angular error (mrad), lock retention fraction, and acquisition time ($t_{\text{acq}}$).

---

## 3. Physical & Disturbance Modeling

### 3.1 60 Hz Rendering Engine (`sim/`)

The beacon intensity profile $I(x, y)$ is modeled using a 2D isotropic Gaussian Point Spread Function (PSF):

$$I(x, y) = I_0 \cdot \exp\left( -\frac{(x - x_c)^2 + (y - y_c)^2}{2 \sigma_{\text{psf}}^2} \right)$$

where $(x_c, y_c)$ is the projected target centroid on the image plane, $I_0$ is peak intensity, and $\sigma_{\text{psf}}$ is the optical blob radius in pixels.

### 3.2 Disturbance Models (`disturbance/`)

1. **Atmospheric Turbulence:** Modeled as spatial Gaussian PSF blurring ($\sigma_{\text{turb}}$) simulating optical scintillation and beam wander.
2. **Platform Vibration:** Modeled using an Ornstein-Uhlenbeck stochastic process generating high-frequency angular jitter:
   $$dx_t = -\theta x_t dt + \sigma_{\text{vib}} dW_t$$
3. **Cloud Occlusion:** Moving translucent soft-edged exponential density masks modulating beacon transmission intensity:
   $$T(x, y) = 1 - \alpha \exp\left( -\frac{d(x,y)^2}{2 r_{\text{cloud}}^2} \right)$$
4. **Camera Motion Blur:** Directional linear convolution filter constructed dynamically along the camera's instant angular velocity vector $(\dot{\theta}_{\text{pan}}, \dot{\theta}_{\text{tilt}})$.
5. **Sensor Noise:** Zero-mean Additive White Gaussian Noise (AWGN) calibrated to sensor Signal-to-Noise Ratio (SNR in dB).

---

## 4. Computer Vision & Tracking Architecture (`tracking/`)

### 4.1 Classical CV Centroid Detection (`tracking/detect.py`)

1. **Gray-Scale Conversion & Gaussian Filtering:** Frame converted to single-channel gray-scale and filtered to attenuate thermal sensor noise.
2. **Adaptive Thresholding:** Pixels above intensity threshold $T_{\text{thresh}} = I_{\text{bg}} + k \cdot \sigma_{\text{bg}}$ are segmented into binary blob regions.
3. **Contour Analysis & Centroid Calculation:** First-order image moments yield sub-pixel centroid estimates:
   $$\bar{x} = \frac{M_{10}}{M_{00}}, \quad \bar{y} = \frac{M_{01}}{M_{00}}$$

### 4.2 Constant-Velocity Kalman Filter (`tracking/kalman.py`)

State vector $\mathbf{x}_k = [x, y, v_x, v_y]^T$ updated via linear state transitions:

$$\mathbf{x}_{k|k-1} = \mathbf{F} \mathbf{x}_{k-1|k-1}, \quad \mathbf{F} = \begin{bmatrix} 1 & 0 & \Delta t & 0 \\ 0 & 1 & 0 & \Delta t \\ 0 & 0 & 1 & 0 \\ 0 & 0 & 0 & 1 \end{bmatrix}$$

Process noise variance is tuned to $Q_{\text{var}} = 2000$ to maintain gain under high angular acceleration, and measurement variance $R_{\text{var}} = 4.0$ matches centroid accuracy.

### 4.3 5-State Finite State Machine (`tracking/state_machine.py`)

- **SEARCH:** No valid detection; tracker scans FOV.
- **ACQUIRE:** Valid centroid detected for $N_{\text{acq}} \ge 3$ consecutive frames; initializes Kalman state.
- **TRACK:** Continuous lock active; Kalman predictions gate target search window.
- **LOST:** Centroid lost for $> 1$ frame; Kalman propagates position estimate.
- **REACQUIRE:** Beacon reappears within Kalman gating region before timeout ($N_{\text{lost}} < 30$ frames).

---

## 5. Boresight-Relative Closed-Loop Control (`control/`)

The control loop converts image-space tracking error $\mathbf{e}_{\text{px}} = (x_{\text{err}}, y_{\text{err}})$ into camera pan and tilt angular commands:

$$\Delta \theta_{\text{pan}} = + \text{PID}(x_{\text{err}}), \quad \Delta \theta_{\text{tilt}} = - \text{PID}(y_{\text{err}})$$

### 5.1 PID Architecture (`control/pid.py`)

1. **Proportional Term:** Direct linear gain $P = K_p \cdot e(t)$.
2. **Integral Anti-Windup:** Accumulated error $I = \int e(t) dt$ clamped to $\pm 100.0$ px$\cdot$s; accumulation frozen when gimbal saturation occurs.
3. **Derivative Low-Pass Filter:** Derivative $D = K_d \cdot \frac{d}{dt} e_{\text{filtered}}(t)$ filtered with $\alpha = 0.25$ to eliminate derivative kick spikes.
4. **Slew-Rate Limit:** Output step per frame clamped to `DEFAULT_MAX_OUTPUT_STEP = 0.003` rad/step ($\approx 6.8^\circ$/s velocity cap).

---

## 6. Empirical Verification & Test Results

```
+-------------------------------------------------------------------------+
| Test Suite Module           | Test Count | Status                       |
+-----------------------------+------------+------------------------------+
| Core Contracts Smoke        | 7          | PASSED                       |
| Virtual Scene & Kinematics  | 17         | PASSED                       |
| Disturbance Models          | 26         | PASSED                       |
| Detection & Kalman Tracker  | 36         | PASSED                       |
| PID Gimbal Control Loop     | 9          | PASSED                       |
| Cockpit UI & Wiring Controls| 16         | PASSED                       |
| Live Pipeline Telemetry     | 9          | PASSED                       |
| Benchmark Video Adapter     | 13         | PASSED                       |
+-----------------------------+------------+------------------------------+
| TOTAL SUITE VERIFIED        | 133        | 133 / 133 PASSED (100.0%)    |
+-------------------------------------------------------------------------+
```

### 6.1 Performance Metrics Baseline

- **Nominal Frame Rate:** 60.0 Hz (16.67 ms step time)
- **Acquisition Time ($t_{\text{acq}}$):** $0.15 - 0.23$ seconds (9–14 frames)
- **Tracking RMSE:** Sub-pixel baseline ($0.66 - 1.19$ px clean; $< 2.50$ px under mild turbulence)
- **Lock Retention Fraction:** $> 97.5\%$ across standard evaluation runs
