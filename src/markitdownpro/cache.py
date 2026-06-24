from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = PROJECT_ROOT / ".cache"


def get_project_cache_dir() -> Path:
    return Path(os.environ.get("MARKITDOWNPRO_CACHE_DIR", DEFAULT_CACHE_DIR)).resolve()


def configure_project_cache() -> Path:
    cache_dir = get_project_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "HF_HOME": cache_dir / "huggingface",
        "HUGGINGFACE_HUB_CACHE": cache_dir / "huggingface" / "hub",
        "HF_HUB_CACHE": cache_dir / "huggingface" / "hub",
        "TORCH_HOME": cache_dir / "torch",
        "XDG_CACHE_HOME": cache_dir,
        "TIKTOKEN_CACHE_DIR": cache_dir / "babeldoc" / "tiktoken",
    }
    for name, path in paths.items():
        path.mkdir(parents=True, exist_ok=True)
        os.environ[name] = str(path)
    os.environ.pop("TRANSFORMERS_CACHE", None)

    return cache_dir


def configure_texteller_cache() -> Path:
    cache_dir = configure_project_cache() / "texteller"
    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        from texteller.globals import Globals
    except Exception:
        return cache_dir

    Globals().cache_dir = cache_dir
    return cache_dir


def configure_babeldoc_cache() -> Path:
    cache_dir = configure_project_cache() / "babeldoc"
    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        import babeldoc.const as const
    except Exception:
        return cache_dir

    const.CACHE_FOLDER = cache_dir
    const.TIKTOKEN_CACHE_FOLDER = cache_dir / "tiktoken"
    const.TIKTOKEN_CACHE_FOLDER.mkdir(parents=True, exist_ok=True)
    os.environ["TIKTOKEN_CACHE_DIR"] = str(const.TIKTOKEN_CACHE_FOLDER)
    return cache_dir


def configure_model_caches() -> Path:
    cache_dir = configure_project_cache()
    configure_texteller_cache()
    configure_babeldoc_cache()
    return cache_dir
