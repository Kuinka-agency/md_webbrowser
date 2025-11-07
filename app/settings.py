"""Configuration helpers bound to python-decouple."""

from __future__ import annotations

from decouple import Config as DecoupleConfig, RepositoryEnv


def load_config(env_path: str = ".env") -> DecoupleConfig:
    """Return a decouple config object anchored to the repository .env file."""

    return DecoupleConfig(RepositoryEnv(env_path))
