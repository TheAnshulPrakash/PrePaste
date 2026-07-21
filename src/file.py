import json
import os
import sys
from pathlib import Path

APP_NAME = "PrePaste"

DEFAULT_CONFIG = {
    "top_margin": 30,
    "right_margin": 10,
    "always_on_top": True,
}


def config_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ["APPDATA"])  # C:\Users\<you>\AppData\Roaming
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))

    folder = base / APP_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "config.json"


def load_config() -> dict:
    path = config_path()

    if not path.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    try:
        with path.open("r", encoding="utf-8") as file:
            return DEFAULT_CONFIG | json.load(file)  # fills in missing settings
    except (json.JSONDecodeError, OSError):
        return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    with config_path().open("w", encoding="utf-8") as file:
        json.dump(config, file, indent=2)
