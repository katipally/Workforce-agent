"""Compatibility shim exposing Config in backend namespace."""

from core.config import Config, env_path

__all__ = ["Config", "env_path"]
