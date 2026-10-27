# codeindex

A token-free code navigation index for a git repository. It answers "where is this defined", "who calls it" and
"which tests cover this file" from a small on-disk index, so a person or a coding agent does not need to grep or read
whole files. Python is parsed with `ast`, JavaScript with regular expressions. No network, no models, standard library only.

## Install

    cp codeindex ~/.local/bin/ && chmod +x ~/.local/bin/codeindex

Add `.index/` to the repository's `.gitignore`. Python 3.11 or newer.

## Configure

- `CODEINDEX_ROOT`: repo root (default: `git rev-parse --show-toplevel`, else the current directory).
- `tests/AREAS.toml` (optional): `[[area]]` tables with `name`, `src` globs and `tests` to map sources to tests when imports do not show it.
- `CODEINDEX_NO_GRAPH=1` and `CODEINDEX_WAIT=1`: if a `graphify` command is on PATH a code graph is refreshed after a build; these skip it or wait for it.

## Example

    codeindex build
    codeindex where parse_file      # symbol definition, file:line
    codeindex callers parse_file    # call sites
    codeindex tests pkg/util.py     # direct and one-hop tests
    codeindex map pkg/              # CODEMAP lines under a prefix

`build` also writes `CODEMAP.md` at the repo root. Run the tests with `python3 -m pytest`.

## License

Apache-2.0, see `LICENSE` and `NOTICE`.
