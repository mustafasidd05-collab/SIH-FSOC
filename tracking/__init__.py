"""tracking/ -- beacon detection, Kalman smoothing/prediction, and the lock
state machine. Depends only on core/contracts.py; the pipeline consumes
SimFrame and emits TrackResult (contract shapes in, contract shape out)."""

from .detect import BeaconDetector, Detection
from .kalman import KalmanTracker
from .pipeline import TrackPipeline
from .state_machine import TrackStateMachine

__all__ = [
    "BeaconDetector",
    "Detection",
    "KalmanTracker",
    "TrackPipeline",
    "TrackStateMachine",
]