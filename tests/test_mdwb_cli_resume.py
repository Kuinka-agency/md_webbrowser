from __future__ import annotations

import csv
import io
import json

import zstandard as zstd
from typer.testing import CliRunner

from scripts import mdwb_cli

runner = CliRunner()


def _rewrite_index(root, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for row in rows:
        writer.writerow(row)
    compressed = zstd.ZstdCompressor().compress(buffer.getvalue().encode("utf-8"))
    (root / "work_index_list.csv.zst").write_bytes(compressed)


def test_resume_status_json(tmp_path):
    manager = mdwb_cli.ResumeManager(tmp_path)
    manager.mark_complete("https://example.com/article")

    result = runner.invoke(
        mdwb_cli.cli,
        [
            "resume",
            "status",
            "--root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["done"] == 1
    assert payload["entries"] == ["https://example.com/article"]


def test_resume_status_hash_only(tmp_path):
    resume_root = tmp_path
    done_dir = resume_root / "done_flags"
    done_dir.mkdir()
    hash_value = mdwb_cli._resume_hash("https://hash-only.example")
    (done_dir / f"done_{hash_value}.flag").write_text("ts", encoding="utf-8")

    result = runner.invoke(
        mdwb_cli.cli,
        [
            "resume",
            "status",
            "--root",
            str(resume_root),
            "--limit",
            "0",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["entries"][0] == f"hash:{hash_value}"


def test_resume_status_counts_flags_missing_index(tmp_path):
    manager = mdwb_cli.ResumeManager(tmp_path)
    url_a = "https://example.com/a"
    url_b = "https://example.com/b"
    manager.mark_complete(url_a)
    manager.mark_complete(url_b)

    hash_a = mdwb_cli._resume_hash(url_a)
    _rewrite_index(tmp_path, [[hash_a, url_a]])

    result = runner.invoke(
        mdwb_cli.cli,
        [
            "resume",
            "status",
            "--root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["done"] == 2  # 1 indexed entry + 1 placeholder hash
    assert payload["total"] == 1  # index only tracks url_a
    assert any(entry.startswith("hash:") for entry in payload["entries"])
