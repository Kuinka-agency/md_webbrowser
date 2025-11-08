# Agent Starter Scripts

These Typer CLIs reuse the main `scripts/mdwb_cli.py` plumbing (settings, HTTP
client, polling) so you can compose lightweight automations without re-implementing
auth or job orchestration.

## Available commands

- `summarize_article`: capture (or reuse via `--job-id`) and print the first *N*
  sentences of the resulting Markdown.
- `generate_todos`: capture/reuse and emit TODO-style bullets (checkboxes, bullet
  lists, headings such as “Next Steps” or “Action Items”). Supports `--json`.

## Usage

```bash
# Summarize a fresh capture
uv run python -m scripts.agents.summarize_article summarize --url https://example.com --sentences 4

# Summarize an existing job id (skips capture)
uv run python -m scripts.agents.summarize_article summarize --job-id job_abc123

# Generate TODOs and emit JSON
uv run python -m scripts.agents.generate_todos todos --url https://status.example --json

# Reuse a job and limit to 5 action items
uv run python -m scripts.agents.generate_todos todos --job-id job_abc123 --limit 5
```

All commands accept `--api-base`, `--http2/--no-http2`, `--profile`, and
`--ocr-policy` just like the main CLI. Credentials and defaults come from
`.env` via `scripts/mdwb_cli.py`.
