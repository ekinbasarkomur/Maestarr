# Getting started

Install it, run it, and verify it works — before reading anything else.

## Install

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

**Always invoke tools through `.venv/bin/`.** A bare `pytest` or `python -m mypy`
picks up whichever interpreter is first on PATH, which is usually the system
Python without this project's dependencies — it then fails misleadingly, or
worse, passes for the wrong reason (`ignore_missing_imports = true` in
`pyproject.toml` masks missing packages from mypy).

## Verify

```sh
.venv/bin/python -m pytest -v tests/unit    # fast, needs no infrastructure
.venv/bin/python -m mypy maestarr/
maestarr hello
maestarr doctor
```

`maestarr doctor` is the one command to reach for when something is wrong:
it validates configuration, and reports each
check independently rather than failing at the first problem.

## Run the server

```sh
maestarr serve
curl -s http://127.0.0.1:8709/health
```

## Run it in Docker

The shared `echo` network is external — every stack in this workspace joins it
rather than owning it, so `docker compose down` never removes it out from under
the others. Create it once:

```sh
docker network create echo    # only the first time, on this machine
```

```sh
docker compose up --build
curl -s http://127.0.0.1:8709/health
```

The host serves on 8709 and the container publishes 8709, on purpose — both can
run at once.

## Where to go next

- [README.md](README.md) — the reading order for the rest of these pages.
- `../CLAUDE.md` — the rules an agent works under, and the architecture facts
  it must not guess.
- `../.claude/project-map.md` — where everything actually lives.
