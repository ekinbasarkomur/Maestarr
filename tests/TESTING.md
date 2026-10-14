# tests/ — layering and strategy

The `tests/`-local reference: what the three directories mean, how to run each
one, and the rules that follow. For the mock policy in full, see
`.claude/rules/testing.md`, which is always loaded.

## The pyramid

```
tests/
  conftest.py     # stays at the root — fixtures apply repo-wide
  TESTING.md      # this file
  unit/           # no Postgres, no network, no server, no subprocess
  integration/    # real Postgres, the truth anchor
  e2e/            # the CLI as a real subprocess, or the real ASGI app
```

**Layer decision rule** — verify it per file, do not assume:

- **`unit/`** — the file still passes with the test database unreachable. No `@pytest.mark.integration` anywhere in it. Pure
  functions, URL/dialect handling, pydantic schema shape, static checks over
  the source tree, and routes that touch no database.
- **`integration/`** — needs real infrastructure. Every test here carries
  `@pytest.mark.integration`, as a module-level `pytestmark` or per test.
- **`e2e/`** — stands up the real ASGI app, or runs the CLI as a genuine
  subprocess with its own interpreter, event loop, and engine cache. A
  background thread is not a substitute; it shares all three.

`conftest.py` stays at the `tests/` root, **unsplit**. Its fixtures reach every
subdirectory through pytest's upward `conftest.py` discovery.

## How to run each layer

```sh
python -m pytest -v tests/unit           # fast inner loop, no infrastructure
python -m pytest -v tests/e2e            # full end-to-end flows
python -m pytest -v                      # everything
python -m pytest -v -m "not integration" # everything that needs no infrastructure
```

**Markers stay authoritative; the directory layout is belt-and-suspenders on top
of them, never the other way around.** `-m "not integration"` selects by marker
regardless of which directory a file lives in; `pytest tests/unit` selects by
path. The two agree because every file is placed by the same rule its markers
already encode.

## Test file basenames must be unique across all three directories

There are no `__init__.py` files under `tests/`, so pytest derives a module name
from the basename alone. Two files named `test_db.py` in different layers
collide, and the run dies at **collection** with `import file mismatch` — before
a single test executes.

Suffix the layer when the same subject is tested in more than one: `test_db.py`
in `unit/` and `test_db_integration.py` in `integration/`.
