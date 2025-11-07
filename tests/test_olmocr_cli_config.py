from __future__ import annotations

import pytest
from decouple import UndefinedValueError

from scripts import olmocr_cli


class DummyConfig:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def __call__(self, name: str, cast=None, default=None):  # noqa: ANN001
        if name in self.values:
            value = self.values[name]
            if cast:
                return cast(value)
            return value
        if default is not None:
            return default
        raise UndefinedValueError(name)


def test_required_config_returns_value():
    config = DummyConfig({"API_BASE_URL": "http://localhost"})
    result = olmocr_cli._required_config(config, "API_BASE_URL")
    assert result == "http://localhost"


def test_required_config_raises_clierror_when_missing():
    config = DummyConfig({})
    with pytest.raises(olmocr_cli.CLIError):
        olmocr_cli._required_config(config, "API_BASE_URL")
