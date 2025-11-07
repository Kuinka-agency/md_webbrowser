import json
from pathlib import Path

import pytest

from scripts import check_env


def write_env(tmp_path: Path, values: dict[str, str]) -> Path:
    env_path = tmp_path / ".env"
    env_lines = [f"{key}={value}" for key, value in values.items()]
    env_path.write_text("\n".join(env_lines))
    return env_path


def test_load_config_missing_env_exits(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        check_env.load_config(tmp_path / ".env")


def test_capture_status_reports_required_and_optional(tmp_path: Path) -> None:
    env_values = {
        "API_BASE_URL": "http://localhost:8000",
        "CFT_VERSION": "chrome-130.0.6723.69",
        "CFT_LABEL": "Stable-1",
        "PLAYWRIGHT_CHANNEL": "cft",
        "OLMOCR_SERVER": "https://olmocr.example/api",
        "OLMOCR_MODEL": "olmocr-2",
        "OCR_MIN_CONCURRENCY": "2",
        "OCR_MAX_CONCURRENCY": "8",
        "BLOCKLIST_PATH": "config/blocklist.json",
        "SCROLL_SHRINK_WARNING_THRESHOLD": "1",
        "OVERLAP_WARNING_RATIO": "0.65",
        "WARNING_LOG_PATH": "ops/warnings.jsonl",
        "MDWB_API_KEY": "secret",
    }
    env_path = write_env(tmp_path, env_values)
    config = check_env.load_config(env_path)

    statuses = check_env.capture_status(config)
    assert len(statuses) == len(check_env.REQUIRED_VARS) + len(check_env.OPTIONAL_VARS)
    status_map = {status.name: status for status in statuses}

    assert status_map["API_BASE_URL"].value == "http://localhost:8000"
    assert status_map["MDWB_API_KEY"].value == "secret"
    # Optional var not provided should be None but not counted as required.
    assert status_map["VIDEO_WARNING_THRESHOLD"].value is None
    assert status_map["VIDEO_WARNING_THRESHOLD"].required is False


def test_print_json_reports_missing_required(capfd: pytest.CaptureFixture[str]) -> None:
    statuses = [
        check_env.VarStatus("API_BASE_URL", "http://localhost:8000", "desc", True),
        check_env.VarStatus("CFT_VERSION", None, "desc", True),
    ]

    exit_code = check_env.print_json(statuses)
    assert exit_code == 1

    out = capfd.readouterr().out
    payload = json.loads(out)
    assert payload[1]["name"] == "CFT_VERSION"
    assert payload[1]["ok"] is False


def test_print_human_success_and_failure(capfd: pytest.CaptureFixture[str]) -> None:
    ok_statuses = [
        check_env.VarStatus("API_BASE_URL", "http://localhost:8000", "desc", True),
        check_env.VarStatus("MDWB_API_KEY", None, "optional", False),
    ]
    exit_code_ok = check_env.print_human(ok_statuses)
    captured = capfd.readouterr()
    assert exit_code_ok == 0
    assert "OPT " in captured.out

    missing_statuses = [
        check_env.VarStatus("API_BASE_URL", None, "desc", True),
    ]
    exit_code_missing = check_env.print_human(missing_statuses)
    captured_missing = capfd.readouterr()
    assert exit_code_missing == 1
    assert "Missing required variables" in captured_missing.out
