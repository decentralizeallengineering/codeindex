---
name: codeindex
description: Navigate a git repository with the codeindex index before grepping or reading whole files. Use when you need to find where a Python/JS/TS symbol, config key or environment variable is defined, who calls a function, which tests cover a file, what a change may break, or a compact view of one function with its callers, callees, tests and recent commits.
---

# codeindex: look it up before you grep

`codeindex` answers navigation questions from a small on-disk index (`.index/`), so one command can replace several
grep and read calls. Run `codeindex build` first in a session, and again after you edit files. It only re-parses
files whose git blob hash changed, so when nothing changed it returns in well under a second.

If the `codeindex` MCP server is connected, its tools (`where`, `find`, `callers`, `tests`, `map`, `context`,
`impact`) take the same arguments and refresh the index themselves; prefer them over the shell.

## Which command

| You want | Run | Instead of |
|---|---|---|
| Everything about one function or class: signature, docstring, body, callers with their line, callees, tests, last 3 commits | `codeindex context NAME --budget 4000` | grep for the name, then read the defining file and each caller file |
| An overview of one file: outline, importers, imports, tests, env/config reads | `codeindex context path/to/file.py` | reading the file |
| What may break if you change something, and the tests to run | `codeindex impact NAME` (or a file path) | tracing callers by hand |
| Where something is defined, including a TOML/JSON key or an env var | `codeindex where NAME` | `grep -rn "def NAME"` |
| Call sites only | `codeindex callers NAME [--resolved]` | `grep -rn "NAME("` |
| Tests for a file or symbol | `codeindex tests PATH` / `codeindex tests NAME` | guessing test file names |
| Symbols whose name contains a word | `codeindex find WORD` | `grep -rn WORD` |
| Repo layout: files, line counts, purpose, key symbols, tests | `codeindex map [DIR/]` | `ls -R`, opening files |
| What changed since a commit, by symbol | `codeindex changed SHA` | reading `git diff` |
| Python code nothing outside tests uses | `codeindex dead` | none |

NAME can be a bare name (`build`), `Class.method`, a dotted Python path (`pkg.mod.func`) or `path#name` for JS/TS
(`web/util.ts#fmt`).

## How far to trust it

- Each caller row is `resolved` (the target came from imports, `import x as y`, `from m import f as g`, aliases,
  `self.`/`super()` with base classes, `x = Cls(); x.m()`, ES/CommonJS imports) or `name-only` (same name, target
  unknown). In `context` output name-only callers are marked `?`. Check name-only rows before relying on them.
- It is static: decorators that register functions, `getattr`, dependency injection and string-built names are
  not seen. `dead` is name-based and conservative; check before deleting anything.
- `context` and `impact` read the working tree; the index can lag behind until the next `codeindex build`.
- Grep is still the right tool for free text: log messages, comments, error strings.

## Worked examples

The examples use a hypothetical `app` package; the output formats are exactly what codeindex prints.

### 1. "How does `parse_config` handle a missing file?"

```
$ codeindex context parse_config --budget 3000
# app.config.parse_config  def  app/config.py:41-77
def parse_config(path: str, strict: bool = False) -> Config:
    """Load a TOML config; fall back to defaults when the file is missing."""
## body (lines 44-77)
    ...
## callers (3 resolved, 1 name-only marked ?)
app/cli.py:18  app.cli.main  | cfg = parse_config(args.config, strict=args.strict)
...
## tests (2)
tests/test_config.py::test_missing_file
```

The body answers the question, and the callers and tests come with it. Do not open `app/config.py` unless the body
was cut (`... +N more lines`); then rerun with a bigger `--budget`, or read only the range in the header.

### 2. "I'm changing the signature of `Store.put`. What do I need to update and test?"

```
$ codeindex impact Store.put
# impact of app.store.Store.put (method app/store.py:88)
callers (depth <= 3): 5 resolved, 1 name-only (marked ?, not expanded)
  d1  app.api.save  app/api.py:30
  d1? app.legacy.sync  app/legacy.py:12
  d2  app.cli.main  app/cli.py:52
...
tests to run (3):
  python3 -m pytest tests/test_api.py tests/test_store.py tests/test_cli.py
reads (1):
  env STORE_URL  app/store.py:90
```

Edit the `d1` call sites. Check the `?` row (it may call a different `put`). Then paste the pytest command.

### 3. "Where does `REQUEST_TIMEOUT` come from?"

```
$ codeindex where REQUEST_TIMEOUT
pyproject.toml:14  toml  tool.app.REQUEST_TIMEOUT = 30
app/http.py:9  env  REQUEST_TIMEOUT  (read in app.http.client)
```

One command finds the config default and the code that reads the env override. Grep would also return every
mention in docs and comments.
