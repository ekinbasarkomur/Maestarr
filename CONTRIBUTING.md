# Contributing to Maestarr

Thanks for helping. Issues, ideas and pull requests are all welcome.

## Before you start

- For anything bigger than a small fix, open an issue first so we can agree on
  the approach.
- Maestarr is **vibecoded**: much of it was written with an AI coding agent and
  reviewed by a human. AI-assisted contributions are fine — please read and test
  what you submit, and say in the PR that you used an assistant.

## Development setup

```bash
git clone https://github.com/ekinbasarkomur/Maestarr.git && cd Maestarr
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
(cd ui && npm ci)

.venv/bin/maestarr serve          # API + built UI on http://127.0.0.1:8709
(cd ui && npm run dev)            # UI with hot reload on :5173, proxied to the API
```

Point the onboarding at your own stack, or at throwaway containers.

## Checks

Everything CI runs, locally:

```bash
.venv/bin/python -m pytest -q     # backend tests (never touch your real stack)
.venv/bin/python -m mypy maestarr # types
(cd ui && npm run verify)         # UI: lint, typecheck, tests
```

## Guidelines

- Keep tools thin: logic lives in `maestarr/ops`, tools in `maestarr/agent/tools.py`
  only wrap it.
- Anything that changes the user's stack must go through an approval.
- Talk to the *arr apps only through their APIs; never edit their databases.
- No secrets, personal data or adult imagery in tests, screenshots or fixtures.
- Add a line to `CHANGELOG.md` under *Unreleased* for user-visible changes.

## Releasing (maintainers)

1. Move the *Unreleased* notes in `CHANGELOG.md` under a new version heading and
   bump `version` in `pyproject.toml` and `maestarr/__init__.py`.
2. Tag and push: `git tag v0.3.0 && git push origin v0.3.0`.
3. The release workflow publishes `ghcr.io/ekinbasarkomur/maestarr` for amd64
   and arm64 and creates the GitHub release from the changelog.
