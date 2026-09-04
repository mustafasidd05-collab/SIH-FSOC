"""config/config_manager.py -- YAML configuration loader and manager."""

from __future__ import annotations

from pathlib import Path
import yaml


class ConfigManager:
    """Manages loading, validation, and saving of simulator configuration YAML files."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        if config_path is None:
            self.config_path = Path(__file__).parent / "default_config.yaml"
        else:
            self.config_path = Path(config_path)

        self.config = self.load()

    def load(self) -> dict:
        """Load YAML configuration from file, falling back to defaults if missing/invalid."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
        
        # Fallback default dict if load fails
        return {
            "simulation": {"width_px": 640, "height_px": 480, "fps": 30.0, "time_scale": 1.0},
            "camera": {"fov_h_deg": 4.0, "fov_v_deg": 3.0, "max_speed_deg_s": 10.0},
            "target": {"size_px": 12, "motion_pattern": "linear"},
            "disturbance": {"profile": "moderate"},
            "tracking": {"use_ai_filter": True, "confidence_threshold": 0.5},
            "control": {"kp": 0.0003, "ki": 0.00005, "kd": 0.00002},
        }

    def save(self, output_path: str | Path | None = None) -> None:
        """Save current configuration dictionary to YAML file."""
        target = Path(output_path) if output_path is not None else self.config_path
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.config, f, default_flow_style=False)


def load_config(path: str | Path | None = None) -> dict:
    return ConfigManager(path).config


def save_config(config_dict: dict, path: str | Path) -> None:
    mgr = ConfigManager(path)
    mgr.config = config_dict
    mgr.save()
