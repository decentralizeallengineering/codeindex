#!/usr/bin/env python3
"""Build-time benchmark on a generated repository.

    python3 bench/bench_build.py [--files 5000] [--keep DIR]

Generates a git repo with N files (about 60% Python, 30% TypeScript/JavaScript, 10% JSON/TOML), commits it, then
times: a full build, three no-change builds, and incremental builds after editing, renaming and deleting one file.
Each timing is the wall time of a `codeindex build` subprocess, so Python start-up is included. Exits 1 if the
slowest no-change build takes 2 s or more.
"""
import argparse, os, random, shutil, subprocess, sys, tempfile, time

CI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "codeindex")

PY = '''"""Module {i}: synthetic service code."""
import os
from pkg{a}.mod{a} import helper_{a}
import pkg{b}.mod{b} as other

LIMIT_{i} = int(os.environ.get("LIMIT_{i}", "10"))


def helper_{i}(x, y=1):
    """Combine x and y."""
    total = x + y
    for k in range(3):
        total += helper_{a}(k)
    return total


def compute_{i}(items):
    out = []
    for it in items:
        out.append(helper_{i}(it) * other.helper_{b}(it))
    return sum(out)


class Service{i}:
    """A service with a few methods."""

    def __init__(self, name):
        self.name = name

    def start(self):
        self.check()
        return compute_{i}([1, 2, 3])

    def check(self):
        if not self.name:
            raise ValueError("name")
        return True

    def stop(self):
        return helper_{i}(0)
'''

TS = '''import {{ fmt{a} }} from "../web{a}/m{a}";
import * as other from "../web{b}/m{b}";

/** Format a value. */
export function fmt{i}(v: number): string {{
  return String(v) + other.tag{b}();
}}

export const tag{i} = (): string => "t{i}";

export class Widget{i} {{
  constructor(private n: number) {{}}
  render(): string {{
    return fmt{a}(this.n) + this.suffix();
  }}
  suffix = () => {{
    return `{{${{this.n}}}}`;
  }};
}}
'''


def gen(root, n, seed=1):
    rnd = random.Random(seed)
    npy, nts = int(n * 0.6), int(n * 0.3)
    ncfg = n - npy - nts
    for i in range(npy):
        d = os.path.join(root, f"pkg{i}"); os.makedirs(d)
        open(os.path.join(d, "__init__.py"), "w").close()
        a, b = rnd.randrange(npy), rnd.randrange(npy)
        open(os.path.join(d, f"mod{i}.py"), "w").write(PY.format(i=i, a=a, b=b))
    for i in range(nts):
        d = os.path.join(root, f"web{i}"); os.makedirs(d)
        a, b = rnd.randrange(nts), rnd.randrange(nts)
        open(os.path.join(d, f"m{i}.ts"), "w").write(TS.format(i=i, a=a, b=b))
    os.makedirs(os.path.join(root, "conf"))
    for i in range(ncfg):
        if i % 2:
            open(os.path.join(root, "conf", f"c{i}.toml"), "w").write(f'[svc{i}]\nport = {8000 + i}\nSETTING_{i} = "on"\n')
        else:
            open(os.path.join(root, "conf", f"c{i}.json"), "w").write(f'{{"svc{i}": {{"port": {8000 + i}, "SETTING_{i}": true}}}}\n')
    # packages count as files too: n source files, plus their __init__.py files
    git = ["git", "-C", root, "-c", "user.name=bench", "-c", "user.email=bench@example.com"]
    subprocess.run(git[:3] + ["init", "-q"], check=True)
    open(os.path.join(root, ".gitignore"), "w").write(".index/\nCODEMAP.md\n")
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-qm", "synthetic"], check=True)


def run(root, *args):
    env = {**os.environ, "CODEINDEX_ROOT": root, "CODEINDEX_NO_GRAPH": "1"}
    t = time.perf_counter()
    p = subprocess.run([sys.executable, CI, *args], cwd=root, env=env, capture_output=True, text=True)
    dt = time.perf_counter() - t
    if p.returncode: sys.exit(f"codeindex {' '.join(args)} failed:\n{p.stdout}{p.stderr}")
    return dt, p.stdout.strip().splitlines()[0] if p.stdout.strip() else ""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--files", type=int, default=5000)
    ap.add_argument("--keep", help="generate into DIR and keep it")
    a = ap.parse_args()
    root = a.keep or tempfile.mkdtemp(prefix="codeindex-bench-")
    try:
        if a.keep: os.makedirs(root, exist_ok=True)
        t = time.perf_counter(); gen(root, a.files)
        tracked = len(subprocess.run(["git", "-C", root, "ls-files"], capture_output=True, text=True).stdout.splitlines())
        print(f"generated {a.files} source/config files ({tracked} tracked incl. __init__.py) in {time.perf_counter() - t:.1f}s: {root}")
        rows = [("full build", *run(root, "build"))]
        nochange = [run(root, "build") for _ in range(3)]
        rows += [(f"no-change build #{k + 1}", *r) for k, r in enumerate(nochange)]
        p = os.path.join(root, "pkg1", "mod1.py")
        with open(p, "a") as fh: fh.write("\n\ndef added_later():\n    return compute_1([4])\n")
        rows.append(("edit 1 file", *run(root, "build")))
        os.rename(os.path.join(root, "pkg2", "mod2.py"), os.path.join(root, "pkg2", "renamed2.py"))
        rows.append(("rename 1 file", *run(root, "build")))
        os.remove(os.path.join(root, "web3", "m3.ts"))
        rows.append(("delete 1 file", *run(root, "build")))
        rows.append(("query: where helper_7", *run(root, "where", "helper_7")))
        rows.append(("query: callers helper_7", *run(root, "callers", "helper_7")))
        rows.append(("query: context Service9.start", *run(root, "context", "Service9.start")))
        w = max(len(r[0]) for r in rows)
        print(f"{'step':<{w}}  seconds  output")
        for name, dt, out in rows: print(f"{name:<{w}}  {dt:7.2f}  {out}")
        worst = max(r[0] for r in nochange)
        ok = worst < 2.0
        print(f"slowest no-change build: {worst:.2f}s (target < 2 s): {'PASS' if ok else 'FAIL'}")
        sys.exit(0 if ok else 1)
    finally:
        if not a.keep: shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
