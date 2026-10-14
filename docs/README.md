# maestarr documentation

*Start here. This page is the entry point and the reading order; every other
page assumes you arrived through it.*

## What this directory is for

There are three guidance surfaces in this repository and they have different
jobs. Putting content in the wrong one is how it goes stale unnoticed:

| Surface | Job | Audience |
| --- | --- | --- |
| `CLAUDE.md` | The rules, and the architecture facts that must not be guessed | Agents |
| `.claude/project-map.md` | Where things *live* — files, tests, commands, entrypoints | Agents |
| `docs/` (here) | **Why** things are the way they are | Humans |

`docs/` teaches. It is written for a competent Python developer with no prior
exposure to this project, trying to make a first change. Explain *why*,
including what was tried and rejected — that is the part a reader cannot
reconstruct from the code.

Rules files are terse because an agent reads them every session. These pages
can afford prose, because a human reads them once.

## Reading order

Read these in order the first time. Each assumes the ones before it.

1. [getting-started.md](getting-started.md) — install it, run it, verify it.
   Do this before reading anything else.
4. **the HTTP surface** — routes, and how a request becomes a response.
5. **the MCP surface** — tools, transports, and why logging must stay off
   stdout.
6. **lifecycle** — one request traced through every layer, naming a real file
   at each hop. Write this page once the vocabulary above exists; it becomes
   the single most useful page in the tree.

Numbered gaps above are pages worth writing as the project grows. Delete the
lines you will not write rather than leaving them as aspirations.

## Keeping these pages true

Documentation that lies is worse than documentation that is missing — a reader
trusts it and is misled. Two habits keep it honest:

- Run the `documenter` agent (`.claude/agents/documenter.md`) after a spec
  packet ships. It reads the diff, not the spec, and updates these pages to
  match what was actually built.
- Once this tree has more than a couple of pages, add a `tests/unit/test_docs.py`
  that machine-checks link resolution, that every repo path named in a fenced
  block exists, and that every documented CLI command is registered. A rename
  that outlives its documentation should fail a test, not rot quietly.
