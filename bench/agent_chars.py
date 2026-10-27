#!/usr/bin/env python3
"""How many characters an agent reads: `codeindex context` versus grep plus reading whole files.

    python3 bench/agent_chars.py [--repo .] [--budget 4000] [--markdown]

For each of 10 questions about this repository the target symbol is fixed in advance. The baselines are what an
agent without the index typically does:
  grep        `grep -rnw NAME` over the tracked files (the output is read in full)
  +def file   grep, then read the whole file that defines NAME
  +all hits   grep, then read every file grep matched
The codeindex column is the output of `codeindex context NAME --budget B`. "calls shown" counts the call sites grep
finds (lines with `NAME(` that are not the definition) whose file:line appears in the pack, so a small pack that
drops callers shows up. The repository is measured at HEAD in a temporary clone, so the work tree is not touched.
"""
import argparse, os, re, shutil, subprocess, sys, tempfile

CI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "codeindex")

QUESTIONS = [
    ("How does an incremental build decide which files to re-parse?", "build"),
    ("How are blob hashes found for tracked, modified and untracked files?", "scan"),
    ("How does a Python call target get resolved through re-exports and base classes?", "resolve"),
    ("How are JS comments, strings and regex literals removed before parsing?", "js_clean"),
    ("How does a context pack stay inside the character budget?", "pack"),
    ("How are TOML keys and their line numbers found?", "parse_toml"),
    ("How does the MCP server validate tool arguments?", "check_args"),
    ("How is the dead-code list printed?", "q_dead"),
    ("How does `changed` decide a symbol changed?", "q_changed"),
    ("How is a relative JS import mapped to a file?", "js_file"),
]


def sh(cmd, cwd, env=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env).stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=os.path.join(os.path.dirname(CI)))
    ap.add_argument("--budget", type=int, default=4000)
    ap.add_argument("--markdown", action="store_true", help="print a Markdown table")
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="codeindex-chars-")
    try:
        work = os.path.join(tmp, "repo")
        subprocess.run(["git", "clone", "-q", "--no-hardlinks", os.path.abspath(a.repo), work], check=True)
        head = sh(["git", "rev-parse", "--short", "HEAD"], work).strip()
        env = {**os.environ, "CODEINDEX_ROOT": work, "CODEINDEX_NO_GRAPH": "1"}
        ci = [sys.executable, os.path.join(work, "codeindex")]
        subprocess.run(ci + ["build"], cwd=work, env=env, check=True, capture_output=True)
        tracked = sh(["git", "ls-files"], work).split()
        rows = []
        for q, name in QUESTIONS:
            g = sh(["grep", "-nw", name, *tracked], work)
            hits = sorted({ln.split(":", 1)[0] for ln in g.splitlines()})
            wh = sh(ci + ["where", name], work, env).splitlines()
            deff = wh[0].split(":")[0] if wh and wh[0] != "none" else (hits[0] if hits else "")
            size = lambda f: len(open(os.path.join(work, f), encoding="utf-8", errors="replace").read())
            pack = sh(ci + ["context", name, "--budget", str(a.budget)], work, env)
            calls = [ln for ln in g.splitlines() if re.search(rf"\b{re.escape(name)}\s*\(", ln.split(":", 2)[2])
                     and not re.match(rf"\s*(def|class|function)\s+{re.escape(name)}\b", ln.split(":", 2)[2])]
            shown = sum(1 for ln in calls if ":".join(ln.split(":", 2)[:2]) + " " in pack or ":".join(ln.split(":", 2)[:2]) + "?" in pack)
            rows.append((q, name, len(g), len(g) + (size(deff) if deff else 0), len(g) + sum(size(f) for f in hits),
                         len(pack), f"{shown}/{len(calls)}"))
        tot = [sum(r[i] for r in rows) for i in (2, 3, 4, 5)]
        if a.markdown:
            print(f"Measured at commit {head}, `--budget {a.budget}`; characters an agent reads.\n")
            print("| question | symbol | grep | grep + def file | grep + all hit files | codeindex context | calls shown |")
            print("|---|---|---:|---:|---:|---:|---:|")
            for r in rows: print(f"| {r[0]} | `{r[1]}` | {r[2]:,} | {r[3]:,} | {r[4]:,} | {r[5]:,} | {r[6]} |")
            print(f"| **total** | | {tot[0]:,} | {tot[1]:,} | {tot[2]:,} | {tot[3]:,} | |")
        else:
            print(f"commit {head}, budget {a.budget}")
            print(f"{'symbol':<11} {'grep':>7} {'+def':>8} {'+hits':>8} {'context':>8}  calls shown")
            for r in rows: print(f"{r[1]:<11} {r[2]:>7} {r[3]:>8} {r[4]:>8} {r[5]:>8}  {r[6]}")
            print(f"{'total':<11} {tot[0]:>7} {tot[1]:>8} {tot[2]:>8} {tot[3]:>8}")
        print(f"\ncontext / (grep + def file) = {tot[3] / tot[1]:.3f}; context / grep alone = {tot[3] / tot[0]:.2f}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
