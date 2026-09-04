# AGENTS.md — FSOC Coarse-Alignment Virtual Tracking Simulator (SIH 26169)

This file is the constitution for every agent (primary or subagent) working in this
repository. Read this in full before touching any file. If anything you're about to do
conflicts with this document, stop and flag it instead of proceeding.

## 1. What this project is

A software-only simulator that stands in for expensive FSOC (Free Space Optical
Communication) hardware. It must, entirely in software:

- Render a configurable virtual scene with one or more moving optical beacons
- Model a virtual pan-tilt camera with a finite field of view
- Inject realistic disturbances: atmospheric turbulence, platform vibration, sensor noise
- Detect the beacon automatically and track it continuously via computer vision
- Close the loop: drive the virtual camera to keep the beacon centered
- Report live telemetry (FPS, tracking error, lock retention, acquisition time) and export
  a performance log at the end of a run

The judged deliverables are: a standalone executable, documented source code, a technical
report, a user manual, and an auto-generated performance log. Every module you build should
be justifiable in one paragraph of the technical report — write code you could defend live.

## 2. Architecture (do not deviate without flagging it)

- **Language/runtime:** Python 3.11+ for the simulation engine, computer vision, control
  loop, and disturbance models (OpenCV, NumPy, SciPy, filterpy for Kalman filtering).
- **UI shell:** PySide6 (Qt for Python), custom QSS + hand-drawn QPainter overlays —
  not default Qt widgets left unstyled, not a Bootstrap/Material look-alike. Dark
  "mission-control" aesthetic: near-black background, one deliberate accent color for
  lock/lost states, monospace numerals for telemetry, no drop-shadow-and-gradient card
  clichés.
- **Packaging:** PyInstaller one-folder build for the standalone executable deliverable.
- **Contracts:** `core/contracts.py` defines every data shape that crosses a module
  boundary (`SimFrame`, `CameraState`, `TargetState`, `TrackResult`, `TelemetryPacket`).
  This file is the source of truth. Never change a contract without updating every
  consumer in the same task and calling it out explicitly in your report.

## 3. Module ownership (how work is chunked for parallel execution)

| Module | Owns | Depends on |
|---|---|---|
| `sim/` | Virtual scene, target motion, camera model, coordinate transforms | `core/contracts.py` only |
| `disturbance/` | Turbulence, vibration jitter, sensor noise injected into frames | `core/contracts.py` only (build/test against a stub frame generator) |
| `tracking/` | Beacon detection, Kalman-filter tracker, SEARCH→ACQUIRE→TRACK→LOST state machine | `core/contracts.py` only (build/test against recorded synthetic clips) |
| `control/` | PID pan-tilt controller consuming tracking error | `tracking/` output contract, `sim/` camera command contract |
| `ui/` | Dashboard, video/overlay view, config panel, charts | `core/contracts.py` only (build against mocked telemetry first) |
| `telemetry/` | Aggregation, metrics computation, performance-log export | All of the above at integration time |

Modules with no dependency beyond `core/contracts.py` can be worked on in parallel by
separate agent sessions. Do not import across module boundaries except through the
contracts file.

## 4. The workflow every agent follows, every task

1. **PLAN.** Before writing or editing anything, state in plain language: what you're
   about to do, exactly which files/modules it touches, what the expected output is, and
   how you will verify it worked. Post this plan and stop.
2. **APPROVAL GATE.** Wait for explicit human approval before touching any file. Do not
   treat silence, a related comment, or your own confidence as approval.
3. **EXECUTE.** Implement exactly what was approved. If reality diverges mid-task (a
   library doesn't behave as expected, a contract needs to change), stop, explain the
   divergence, and re-request approval rather than improvising past it.
4. **SELF-VERIFY.** Run tests/linters if they exist. For simulation/CV code with no
   existing tests, run a concrete sanity check (known synthetic input → check output
   shape, range, and one hand-computed expected value) and show the result.
5. **SELF-DEBUG.** If verification fails, diagnose and fix. Up to 3 self-correction
   attempts. On a 4th failure, stop and escalate to the human with a precise description
   of what's blocking — do not keep guessing silently.
6. **REPORT.** Before ending the turn, update `PROJECT_STATUS.md` and append a dated
   entry to `phase_history.md` (see templates below for what belongs in each).

## 5. Non-negotiable design rules

- No generic AI-app look: no default component styling left unmodified, no gradient-on-
  white cards, no unstyled system font. Every screen should look intentionally designed
  for a mission-control/telemetry context.
- No silent contract changes (see §2).
- No claiming a task is "done" without having run the self-verify step and shown its
  result.
- No new dependency without naming it in the plan step first.

## 6. Files every agent reads on startup

`AGENTS.md` (this file) → `PROJECT_STATUS.md` → `core/contracts.py` → the README of the
module you're about to touch.

## 7. Files every agent updates before finishing a task

`PROJECT_STATUS.md` (current state) and `phase_history.md` (append-only session log).
Never skip this step, even for a small change.
