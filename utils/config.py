"""
Application configuration — backed by config.json.
Auto-created on first run.
"""

import json
import os

DEFAULT_CONFIG = {
    "gemini_api_key": "",
    "openai_api_key": "",
    "deepl_api_key": "",
    "libre_url": "https://libretranslate.com",
    "libre_api_key": "",
    "default_engine": "Argos Translate (Offline)",
    "default_target_lang": "Spanish",
    "cache_path": "cache.json",
    "output_suffix": "_translated",
}

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config.json"
)


def get_config_path() -> str:
    # Prefer AppData on Windows, workspace dir elsewhere
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return os.path.join(appdata, "RenPyTranslatorPro", "config.json")
    return _CONFIG_PATH


def load_config() -> dict:
    path = get_config_path()
    config = dict(DEFAULT_CONFIG)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                stored = json.load(f)
            config.update(stored)
        except Exception:
            pass
    else:
        save_config(config)
    return config


def save_config(config: dict) -> None:
    path = get_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
