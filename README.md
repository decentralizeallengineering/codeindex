# codeindex

[![tests](https://github.com/decentralizeallengineering/codeindex/actions/workflows/tests.yml/badge.svg)](https://github.com/decentralizeallengineering/codeindex/actions/workflows/tests.yml) ![license](https://img.shields.io/badge/license-Apache--2.0-blue)

A token-free code navigation index for a git repository. It answers "where is this defined", "who calls it", "which
tests cover it" and "what breaks if I change it" from a small on-disk index, so a person or a coding agent does not
need to grep and read whole files. One script, standard library only, no network, no models. Python 3.11 or newer.

- **Python** is parsed with `ast`. **JavaScript and TypeScript** are parsed by a comment, string and regex-literal
  stripper plus one event regex over the cleaned text (no dependencies). **TOML and JSON** config keys and
  **environment-variable reads** (`os.environ`, `os.getenv`, `process.env`, `import.meta.env`) are indexed too.
- **Incremental**: a build re-parses only the files whose git blob hash changed.
- **Callers are marked** `resolved` (target known) or `name-only` (same name, target unknown), so you know how much
  to trust each row.

## Install

    cp codeindex ~/.local/bin/ && chmod +x ~/.local/bin/codeindex

Add `.index/` to the repository's `.gitignore`. `build` also writes `CODEMAP.md` at the repo root; commit it or
ignore it.

## Commands

    codeindex build [--full]            index the repo (incremental; --full ignores the previous index)
    codeindex where NAME                definitions of a symbol, config key or env var: file:line
    codeindex find WORD                 symbols whose name contains WORD (case-insensitive)
    codeindex callers NAME [--resolved] call sites, each marked resolved or name-only
    codeindex tests PATH|NAME           tests that import or mention a file (direct, plus one import hop)
    codeindex map [PREFIX]              CODEMAP lines: path | LOC | purpose | key symbols | tests
    codeindex changed SHA               symbols added, removed or changed between SHA and the working tree
    codeindex dead [--limit N]          Python symbols with no references outside tests, largest first
    codeindex context NAME|PATH [--budget 4000]
    codeindex impact NAME|PATH [--depth 3]
    codeindex mcp                       MCP server on stdio

NAME can be a bare name (`build`), `Class.method`, a dotted Python path (`pkg.mod.func`), `path#name` for JS/TS
(`web/util.ts#fmt`), a config key (`tool.app.timeout` or just `timeout`) or an environment variable.

**`context`** prints one pack within a character budget: the definition with its signature and docstring, the body
(or its top), callers as `file:line` plus the calling line, callees, the tests that cover it, and the last 3
commits that touched those lines (`git log -L`, falling back to the file's history). For a class, the body section
is the member outline; for a file, it is the outline, importers, imports, tests and env/config reads. Sections share
the budget by fixed weights, unused share moves to the others, and each section is cut at a line boundary with a
`... +N more lines` marker. A section too small to show anything is named in a closing `skipped:` line. The output is
never longer than the budget, and the same index gives the same output.

**`impact`** lists callers up to `--depth` (resolved edges are followed; name-only matches are listed once, marked
`?`, and not followed), the files involved, the tests to run as a ready-to-paste `python3 -m pytest ...` command (JS
tests listed separately), and the env vars and config keys read by the symbol and its callees.

**`changed SHA`** parses both versions of every file in `git diff SHA` (plus untracked files) and compares
symbols by qualified name. A symbol counts as changed when its own lines change; a class is not marked changed
because one of its methods was, and moving code is not a change.

**`dead`** lists Python functions, methods and classes outside tests whose name never appears outside tests and
outside their own body, as a name, attribute, string literal, import or config entry point (`"pkg.cli:main"`). The
check is name-based, so it errs toward keeping things. Rows are flagged `@decorator` and `ext-base` (a method of a
class with a base outside the repo, for example an overridden hook). Check before deleting anything.

## How callers are resolved

A row is `resolved` when the target is known from the code itself:

| Python | JavaScript / TypeScript |
|---|---|
| `import pkg.mod` then `pkg.mod.f()`; `import pkg.mod as m` then `m.f()` | `import { f } from './x'`, `import { f as g }`, `import d from './x'` |
| `from pkg.mod import f as g`, relative imports, re-exports in `__init__.py`, `from x import *` | `import * as ns from './x'` then `ns.f()` |
| aliases: `g = pkg.mod.f` (module or function scope), `h = self.method` | `const x = require('./x')`, `const { f } = require('./x')` |
| `self.m()` / `cls.m()`, looked up through base classes; `super().m()` | `export {...} from`, `export * from`, `module.exports = {...}`, `exports.f =` |
| `x = Cls(); x.m()` | `this.m()` in a class; functions of the same file |
| external targets: `os.path.join`, `builtins.len` | globals: `console.log`, `JSON.parse` |

Everything else is `name-only`: method calls on parameters and attributes of unknown type, dynamic dispatch,
`getattr`. Relative JS specifiers resolve against the importing file (`./x` to `x.ts`, `x.tsx`, `x.js`,
`x/index.ts`, ...; a `.js` specifier also finds the `.ts` file). Bare package specifiers are external. TS path
aliases (`@/x`) are not resolved.

Tests are mapped by imports, string literals naming a module path or file (`mock.patch("pkg.mod.f")`,
`"pkg/mod.py"`), a unique file basename (tests that run a script by name), and optional `tests/AREAS.toml` with
`[[area]]` tables of `name`, `src` globs and `tests`. Test files are `tests/`, `test/`, `__tests__/`, `test_*.py`,
`*_test.py`, `conftest.py` and `*.test.*` / `*.spec.*`.

## Incremental builds

`.index/hashes.tsv` holds each indexed file's git blob hash. Clean tracked files take their hash from the git index
(`git ls-files -s`) without being read; modified and untracked files are hashed the way git hashes them. If no hash
changed, the build stops there. Otherwise only the changed files are re-parsed (parse results are cached in
`.index/parsed.json` and do not depend on other files), and then call targets, tests and dead code are relinked for
the whole repo. A change to `FORMAT` in the script, a missing index file, or `--full` forces a full rebuild.

`python3 bench/bench_build.py --files 5000` generates a synthetic repository and times each step: 3,000 Python
modules, each in its own package with an `__init__.py`; 1,500 TypeScript files; 500 JSON/TOML files. That is 8,000
indexed files. Measured on a 4-core Linux container, Python 3.13:

| step | seconds |
|---|---:|
| full build | 2.98 |
| no-change build (slowest of 3) | 0.12 |
| edit 1 file | 1.43 |
| rename 1 file | 1.70 |
| delete 1 file | 1.16 |
| `where` / `callers` / `context` query | 0.12 / 0.12 / 0.18 |

Times are wall time of a `codeindex` subprocess, Python start-up included. The script exits non-zero if a
no-change build takes 2 s or more.

## For coding agents

### MCP server

`codeindex mcp` speaks MCP over stdio (newline-delimited JSON-RPC 2.0: `initialize`, `ping`, `tools/list`,
`tools/call`) and exposes the tools `where`, `find`, `callers`, `tests`, `map`, `context` and `impact`. Each has a
JSON Schema with `additionalProperties: false`, and every tool is marked read-only. Before a tool call it refreshes
the index if the last refresh was more than 2 s ago, which costs one no-change build when nothing changed
(`CODEINDEX_MCP_NOBUILD=1` turns this off). Logs go to stderr.

For Claude Code, put this in `.mcp.json` at the project root:

```json
{
  "mcpServers": {
    "codeindex": {
      "type": "stdio",
      "command": "codeindex",
      "args": ["mcp"]
    }
  }
}
```

or run `claude mcp add --transport stdio --scope project codeindex -- codeindex mcp`. Claude Code sets
`CLAUDE_PROJECT_DIR` for the server, and `codeindex mcp` uses it to find the repository. For other clients, set
`CODEINDEX_ROOT` in the server's `env`, or start it inside the repository.

### Skill

`skills/codeindex/SKILL.md` tells an agent which command to use before grepping, with three worked examples. Copy
the folder to `.claude/skills/codeindex/` in a project or to `~/.claude/skills/codeindex/` for all projects.

### What it saves: measured

`python3 bench/agent_chars.py --markdown` takes 10 questions about this repository, each with a target symbol fixed
in advance. For each one it counts the characters an agent reads with `codeindex context NAME --budget 4000`, and
with grep (`grep -nw NAME` over tracked files) plus reading whole files. It runs on a clean clone of HEAD.

Measured at commit 93809fd:

| question | symbol | grep | grep + def file | grep + all hit files | codeindex context | calls shown |
|---|---|---:|---:|---:|---:|---:|
| How does an incremental build decide which files to re-parse? | `build` | 3,589 | 89,094 | 124,947 | 3,928 | 2/3 |
| How are blob hashes found for tracked, modified and untracked files? | `scan` | 178 | 85,683 | 90,731 | 1,656 | 1/1 |
| How does a Python call target get resolved through re-exports and base classes? | `resolve` | 619 | 86,124 | 91,172 | 1,296 | 6/6 |
| How are JS comments, strings and regex literals removed before parsing? | `js_clean` | 317 | 85,822 | 90,870 | 867 | 1/1 |
| How does a context pack stay inside the character budget? | `pack` | 1,439 | 86,944 | 91,992 | 2,763 | 3/3 |
| How are TOML keys and their line numbers found? | `parse_toml` | 190 | 85,695 | 90,743 | 2,295 | 1/1 |
| How does the MCP server validate tool arguments? | `check_args` | 206 | 85,711 | 90,759 | 1,322 | 1/1 |
| How is the dead-code list printed? | `q_dead` | 200 | 85,705 | 90,753 | 990 | 1/1 |
| How does `changed` decide a symbol changed? | `q_changed` | 199 | 85,704 | 90,752 | 2,677 | 1/1 |
| How is a relative JS import mapped to a file? | `js_file` | 381 | 85,886 | 90,934 | 1,431 | 4/4 |
| **total** | | 7,318 | 862,368 | 943,653 | 19,225 | |

How to read it:

- "calls shown" counts the grep lines that look like calls (`NAME(`, excluding the definition) whose `file:line` is
  in the pack. The one miss for `build` is a docstring line ("after a build (CODEINDEX_NO_GRAPH=1 ..."), not a call.
- This repository is mostly one ~1,700-line file, so "read the defining file" means reading about 85,000
  characters. That favours codeindex. In a repository of small files the gap is smaller.
- The pack is about 2.6 times as long as grep output alone, but grep output does not contain the code.
- The table measures characters read. It does not measure whether the pack was enough to answer the question; a
  truncated body (`... +N more lines`) may still need a targeted read.

## Configure

- `CODEINDEX_ROOT`: repo root (default: `git rev-parse --show-toplevel`, else the current directory; inside a linked
  worktree without its own index, the main checkout's index is used).
- `tests/AREAS.toml` (optional): see above.
- `CODEINDEX_NO_GRAPH=1` and `CODEINDEX_WAIT=1`: if a `graphify` command is on PATH a code graph is refreshed after
  a build; these skip it or wait for it.

## Index files

All in `.index/`: `hashes.tsv` (path, blob sha, language), `parsed.json` (per-file parse cache), `symbols.tsv`,
`callers.tsv`, `testmap.tsv`, `deps.tsv`, `reads.tsv`, `dead.tsv`, `areas.tsv`, `CODEMAP.md`, `meta.json`. Files are
replaced atomically, and a lock serialises concurrent builds.

## Tests

    python3 -m pytest

Each test generates its fixture repository with git in a temp dir. Together they cover every command, the Python
and JS/TS resolution cases above, config keys and env vars, incremental edit, rename and delete, a format-version
rebuild, the context budget, impact, and an MCP round trip. They run in about 8 s.

## License

Apache-2.0, see `LICENSE` and `NOTICE`.
