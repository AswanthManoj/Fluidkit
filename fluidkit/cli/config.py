import json
from pathlib import Path


DEFAULT_CONFIG = {
    "entry": "src/app.py",
    "host": "0.0.0.0",
    "backend_port": 8000,
    "frontend_port": 5173,
    "schema_output": "src/lib/fluidkit",
    "watch_pattern": "src/**/*.py",
    "secure": True,
}


def load_config(overrides: dict = {}) -> dict:
    config = DEFAULT_CONFIG.copy()
    config_path = Path("fluidkit.config.json")
    if config_path.exists():
        config.update(json.loads(config_path.read_text(encoding="utf-8")))
    config.update({k: v for k, v in overrides.items() if v is not None})
    return config


def write_default_config(project_root: str = ".") -> None:
    config_path = Path(project_root) / "fluidkit.config.json"
    if config_path.exists():
        return
    config_path.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
