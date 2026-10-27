import json, os, subprocess, sys

import pytest

CI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "codeindex")
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "init.defaultBranch=main"]


def ci(repo, *args):
    env = {**os.environ, "CODEINDEX_NO_GRAPH": "1", "CODEINDEX_ROOT": str(repo)}
    return subprocess.run([sys.executable, CI, *args], cwd=repo, capture_output=True, text=True, env=env, timeout=60)


def out(repo, *args):
    r = ci(repo, *args)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def write(repo, files):
    for path, text in files.items():
        p = repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


def make_repo(path, files, commit=True):
    """A fixture repo generated with git in a temp dir."""
    write(path, files)
    subprocess.run(GIT + ["init", "-q", str(path)], check=True)
    if commit:
        commit_all(path, "init")
    assert ci(path, "build").returncode == 0
    return path


def commit_all(path, msg):
    subprocess.run(GIT + ["-C", str(path), "add", "-A"], check=True)
    subprocess.run(GIT + ["-C", str(path), "commit", "-qm", msg], check=True)
    return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def row(text, *needles):
    """The output line containing every needle."""
    hits = [ln for ln in text.splitlines() if all(n in ln for n in needles)]
    assert hits, f"no line with {needles} in:\n{text}"
    return hits[0]


PY = {
    "pkg/__init__.py": "from .util import add_one\n",
    "pkg/util.py": (
        '"""Helpers."""\nimport os\n\n'
        'def add_one(x):\n    """Add one."""\n    return x + 1\n\n'
        "def unused_helper(a, b):\n    total = a + b\n    total += 1\n    return total\n\n"
        "def tiny():\n    return 0\n\n"
        "class Base:\n    def greet(self):\n        return 'hi'\n\n"
        "class Child(Base):\n"
        "    def run(self):\n        t = os.environ.get('APP_TIMEOUT')\n        return self.greet() + str(add_one(1))\n"
        "    def again(self):\n        return super().greet()\n"
    ),
    "pkg/main.py": (
        "import os\nimport pkg.util\nfrom pkg.util import add_one as inc, Child\nfrom . import util as u\n\n"
        "def run():\n    f = pkg.util.add_one\n    c = Child()\n    c.run()\n    key = os.getenv('API_KEY')\n"
        "    return inc(1) + f(2) + u.add_one(3) + mystery(4)\n\n"
        "def entry():\n    return run() + tiny_alias()\n\n"
        "tiny_alias = pkg.util.tiny\n"
    ),
    "tests/test_util.py": "from pkg.util import add_one\n\ndef test_it():\n    assert add_one(1) == 2\n",
    "tests/test_main.py": "from pkg.main import entry\n\ndef test_entry():\n    assert entry()\n",
    "scripts/runme.py": "def go():\n    return 1\n",
    "tests/test_runme.py": "import subprocess, sys\n\ndef test_run():\n    subprocess.run([sys.executable, 'runme.py'])\n",
    "pyproject.toml": '[tool.app]\nSOME_SETTING = 30\nrequest_timeout = 5\n\n[project.scripts]\napp = "pkg.main:entry"\n',
    "web/config.json": '{\n  "server": {\n    "port": 8080,\n    "SOME_SETTING": "x"\n  }\n}\n',
}

JS = {
    "web/util.ts": (
        "/** Format a name. */\nexport function fmt(name: string): string {\n  return name.trim();\n}\n"
        "export const twice = (n: number) => n * 2;\n"
        "export class Greeter {\n  constructor(private who: string) {}\n"
        "  greet(): string { return fmt(this.who) + this.tail(); }\n"
        "  tail = () => {\n    return `!${'}'}`;\n  };\n}\n"
        "export interface Shape { area(): number; }\n"
    ),
    "web/app.js": (
        "import { fmt, Greeter as G } from './util';\nimport * as U from './util.js';\n"
        "const lib = require('./lib');\nconst { helper } = require('./lib');\n"
        "// fmt('in a comment') is not a call\n"
        "function main() {\n  const url = process.env.API_URL;\n  const { NODE_ENV } = process.env;\n"
        "  console.log(fmt('a'), U.twice(2), helper(), lib.helper(), /fmt\\(/.test('x'));\n"
        "  return new G('x').greet();\n}\nmodule.exports = { main };\n"
    ),
    "web/lib.js": "function helper() { return 'h'; }\nexports.helper = helper;\n",
    "web/app.test.js": "const { main } = require('./app');\ntest('main', () => { main(); });\n",
}


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    return make_repo(tmp_path_factory.mktemp("repo"), {**PY, **JS})


def test_help():
    r = subprocess.run([sys.executable, CI, "--help"], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and "codeindex build" in r.stdout and "codeindex mcp" in r.stdout


def test_build_where_callers_tests(tmp_path):
    (tmp_path / "pkg").mkdir(); (tmp_path / "tests").mkdir()
    (tmp_path / "pkg" / "util.py").write_text('"""Helpers."""\n\ndef add_one(x):\n    """Add one."""\n    return x + 1\n')
    (tmp_path / "pkg" / "main.py").write_text("from pkg.util import add_one\n\ndef run():\n    return add_one(1)\n")
    (tmp_path / "tests" / "test_util.py").write_text("from pkg.util import add_one\n\ndef test_it():\n    assert add_one(1) == 2\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert ci(tmp_path, "build").returncode == 0
    assert "pkg/util.py:3" in ci(tmp_path, "where", "add_one").stdout
    assert "pkg/main.py:4" in ci(tmp_path, "callers", "add_one").stdout
    assert "tests/test_util.py" in ci(tmp_path, "tests", "pkg/util.py").stdout


# ---------------------------------------------------------------- commands

def test_where(repo):
    assert "pkg/util.py:4  def  pkg.util.add_one(x)  Add one." in out(repo, "where", "add_one")
    assert "pkg/util.py:21" in out(repo, "where", "Child.run")           # Class.method
    assert "pkg/util.py:21" in out(repo, "where", "pkg.util.Child.run")  # fully qualified
    assert "none" in out(repo, "where", "no_such_symbol")


def test_find(repo):
    o = out(repo, "find", "HELP")                                         # case-insensitive substring
    assert "pkg.util.unused_helper" in o and "web/lib.js#helper" in o


def test_callers_rows_are_marked(repo):
    o = out(repo, "callers", "mystery")
    assert "0 resolved, 1 name-only" in o and "name-only" in row(o, "pkg/main.py:11")


def test_tests_command(repo):
    o = out(repo, "tests", "pkg/util.py")
    assert "direct: tests/test_util.py" in o
    assert "tests/test_main.py" in row(o, "indirect")                    # pkg/main.py imports util; its test is 1 hop
    assert "web/app.test.js" in out(repo, "tests", "web/app.js")
    assert "tests/test_runme.py" in out(repo, "tests", "scripts/runme.py")          # runs the script by file name
    assert "tests/test_util.py::test_it" in out(repo, "tests", "add_one")  # a symbol: the tests that call it


def test_map(repo):
    o = out(repo, "map", "pkg/")
    assert "pkg/util.py | 25 | Helpers. |" in o and "test_util.py" in row(o, "pkg/util.py")
    assert (repo / "CODEMAP.md").exists()


# ---------------------------------------------------------------- Python callers accuracy

def test_python_module_func_and_import_as(repo):
    o = out(repo, "callers", "pkg.util.add_one")
    for loc in ("pkg/main.py:11", "pkg/util.py:23", "tests/test_util.py:4"):
        assert "resolved" in row(o, loc)
    # inc(1) (from x import y as z), u.add_one (from . import util as u), f(2) (alias f = pkg.util.add_one)
    calls = [ln for ln in o.splitlines() if "pkg/main.py:11" in ln]
    assert len(calls) == 3 and all("-> pkg.util.add_one" in ln for ln in calls)


def test_python_self_super_and_instance(repo):
    o = out(repo, "callers", "Base.greet")
    assert "pkg.util.Child.run -> pkg.util.Base.greet" in row(o, "pkg/util.py:23")   # self.greet() inherited
    assert "pkg.util.Child.again -> pkg.util.Base.greet" in row(o, "pkg/util.py:25")  # super().greet()
    assert "pkg.main.run -> pkg.util.Child.run" in out(repo, "callers", "Child.run")   # c = Child(); c.run()


def test_python_module_alias(repo):
    assert "pkg.main.entry -> pkg.util.tiny" in out(repo, "callers", "tiny")          # tiny_alias = pkg.util.tiny


# ---------------------------------------------------------------- JavaScript / TypeScript

def test_js_definitions(repo):
    assert "web/util.ts:2  function  web/util.ts#fmt(name: string)  Format a name." in out(repo, "where", "fmt")
    assert "web/util.ts:5  function" in out(repo, "where", "twice")                   # arrow function in const
    assert "web/util.ts:6  class" in out(repo, "where", "Greeter")
    assert "web/util.ts:8  method" in out(repo, "where", "Greeter.greet")
    assert "web/util.ts:9  method" in out(repo, "where", "Greeter.tail")             # arrow class field
    assert "web/util.ts:13  interface" in out(repo, "where", "Shape")
    assert "area" not in out(repo, "find", "area")                                   # interface members are not code


def test_js_imports_exports_and_calls(repo):
    o = out(repo, "callers", "fmt")
    assert "web/app.js#main -> web/util.ts#fmt" in row(o, "web/app.js:9")             # ES named import
    assert "web/util.ts#Greeter.greet -> web/util.ts#fmt" in o
    assert "web/app.js:5" not in o                                                    # comment, not a call
    assert "-> web/util.ts#twice" in out(repo, "callers", "twice")                   # import * as U; U.twice()
    o = out(repo, "callers", "helper")
    assert o.count("-> web/lib.js#helper") == 2                                       # require + destructuring
    assert "-> web/util.ts#Greeter.tail" in out(repo, "callers", "tail")             # this.tail()
    assert "-> web/app.js#main" in out(repo, "callers", "main")                      # module.exports = { main }
    assert "-> console.log" in out(repo, "callers", "log")


# ---------------------------------------------------------------- config keys and env vars

def test_config_keys_and_env(repo):
    o = out(repo, "where", "SOME_SETTING")
    assert "pyproject.toml:2  toml  tool.app.SOME_SETTING = 30" in o
    assert "web/config.json:4  json  server.SOME_SETTING = \"x\"" in o
    assert "pyproject.toml:6" in out(repo, "where", "project.scripts.app")
    assert "pkg/util.py:22  env  APP_TIMEOUT  (read in pkg.util.Child.run)" in out(repo, "where", "APP_TIMEOUT")
    assert "pkg/main.py:10  env  API_KEY" in out(repo, "where", "API_KEY")             # os.getenv
    assert "web/app.js:7  env  API_URL" in out(repo, "where", "API_URL")               # process.env.X
    assert "web/app.js:8  env  NODE_ENV" in out(repo, "where", "NODE_ENV")             # const { X } = process.env


# ---------------------------------------------------------------- dead and changed

def test_dead(repo):
    o = out(repo, "dead")
    lines = o.splitlines()[1:]
    assert "pkg.util.unused_helper" in lines[0]                                       # largest first
    assert any("pkg.util.Child.again" in ln for ln in lines)
    for alive in ("add_one", "pkg.util.tiny", "pkg.main.entry", "Base.greet"):        # entry: pyproject script
        assert not any(ln.endswith(alive) or alive + " " in ln for ln in lines), alive


def test_changed(tmp_path):
    r = make_repo(tmp_path, {"m.py": "def a():\n    return 1\n\ndef b():\n    return 2\n\nclass K:\n    def m(self):\n        return 3\n",
                             "c.toml": "[x]\nk = 1\n"})
    base = subprocess.run(["git", "-C", str(r), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    write(r, {"m.py": "def a():\n    return 10\n\nclass K:\n    def m(self):\n        return 3\n\ndef c():\n    return 4\n",
              "c.toml": "[x]\nk = 2\n", "n.ts": "export function z() {}\n"})
    o = out(r, "changed", base)
    assert "~ def      a  m.py:1" in o
    assert "- def      b  m.py:4" in o
    assert "+ def      c  m.py:8" in o and "+ function z  n.ts:1" in o
    assert "~ toml     x.k  c.toml:2" in o
    assert "K" not in o                                                               # moved but unchanged
    assert "unknown commit" in out(r, "changed", "nope")


# ---------------------------------------------------------------- incremental build

def test_incremental_edit_rename_delete(tmp_path):
    r = make_repo(tmp_path, {"a.py": "def f():\n    return 1\n", "b.py": "from a import f\n\ndef g():\n    return f()\n",
                             "c.py": "def h():\n    return 2\n"}, commit=False)
    assert "(0 reparsed)" in out(r, "build") and "up to date" in out(r, "build")
    write(r, {"a.py": "def f():\n    return 1\n\ndef f2():\n    return f()\n"})                      # edit
    assert "(1 reparsed)" in out(r, "build")
    assert "a.py:4" in out(r, "where", "f2") and "a.f2 -> a.f" in out(r, "callers", "f")
    (r / "a.py").rename(r / "core.py")                                                              # rename
    write(r, {"b.py": "from core import f\n\ndef g():\n    return f()\n"})
    assert "(2 reparsed)" in out(r, "build")
    assert "core.py:1" in out(r, "where", "f") and "a.py" not in out(r, "where", "f")
    assert "b.g -> core.f" in out(r, "callers", "f")
    (r / "c.py").unlink()                                                                           # delete
    o = out(r, "build")
    assert "2 files (0 reparsed)" in o
    assert "none" in out(r, "where", "h")


def test_format_version_change_forces_full_rebuild(tmp_path):
    r = make_repo(tmp_path, {"a.py": "def f():\n    pass\n", "b.py": "def g():\n    pass\n"})
    meta = json.loads((r / ".index" / "meta.json").read_text())
    (r / ".index" / "meta.json").write_text(json.dumps({**meta, "format": 1}))
    assert "2 files (2 reparsed)" in out(r, "build")
    assert "2 files (2 reparsed)" in out(r, "build", "--full")


# ---------------------------------------------------------------- context and impact

def test_context_sections(repo):
    o = out(repo, "context", "add_one")
    assert o.startswith("# pkg.util.add_one  def  pkg/util.py:4-6\ndef add_one(x):\n    \"\"\"Add one.\"\"\"\n")
    assert "## body (lines 5-6)" in o and "    return x + 1" in o
    assert "pkg/main.py:11  pkg.main.run  | return inc(1) + f(2)" in o
    assert "tests/test_util.py::test_it" in o
    assert "## commits (touching these lines)" in row(o, "## commits") and " init" in o
    o = out(repo, "context", "Child.run")
    assert "L22 os.environ.get" in o and "L23 pkg.util.Base.greet" in o              # callees
    assert "## members (2)" in out(repo, "context", "Child")
    assert "## outline" in out(repo, "context", "web/util.ts")                         # a file


def test_context_respects_budget(repo):
    for target in ("add_one", "Child", "web/app.js", "pkg/util.py", "SOME_SETTING"):
        for budget in (200, 400, 900, 4000):
            o = out(repo, "context", target, "--budget", str(budget))
            assert len(o) <= budget, (target, budget, len(o))
            assert o == out(repo, "context", target, "--budget", str(budget))      # deterministic
    small, big = out(repo, "context", "Child", "--budget", "300"), out(repo, "context", "Child", "--budget", "4000")
    assert ("more lines" in small or "skipped:" in small) and big.startswith(small.splitlines()[0])


def test_impact(repo):
    o = out(repo, "impact", "tiny")
    assert "d1  pkg.main.entry" in o                                                  # via the module alias
    assert "d2  tests.test_main.test_entry" in o                                     # transitive
    assert "python3 -m pytest tests/test_main.py" in o
    o = out(repo, "impact", "pkg.util.Child.run")
    assert "d1  pkg.main.run" in o and "d2  pkg.main.entry" in o and "d3  tests.test_main.test_entry" in o
    assert "env APP_TIMEOUT  pkg/util.py:22" in o
    o = out(repo, "impact", "pkg.main.run", "--depth", "1")
    assert "env API_KEY" in o and "env APP_TIMEOUT" in row(o, "APP_TIMEOUT", "via pkg.util.Child.run")
    assert "d2" not in o
    o = out(repo, "impact", "pkg/util.py")
    assert "tests/test_util.py" in row(o, "python3 -m pytest")


# ---------------------------------------------------------------- MCP

def test_mcp_round_trip(repo):
    env = {**os.environ, "CODEINDEX_NO_GRAPH": "1", "CODEINDEX_ROOT": str(repo)}
    p = subprocess.Popen([sys.executable, CI, "mcp"], cwd=repo, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)
    def rpc(msg):
        p.stdin.write(json.dumps(msg) + "\n"); p.stdin.flush()
        return json.loads(p.stdout.readline()) if "id" in msg else None
    try:
        init = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
        assert init["result"]["protocolVersion"] == "2025-06-18" and "tools" in init["result"]["capabilities"]
        rpc({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
        assert sorted(t["name"] for t in tools) == ["callers", "context", "find", "impact", "map", "tests", "where"]
        assert all(t["inputSchema"]["additionalProperties"] is False for t in tools)
        res = rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "context", "arguments": {"target": "add_one", "budget": 600}}})["result"]
        assert res["isError"] is False and res["content"][0]["text"].startswith("# pkg.util.add_one") and len(res["content"][0]["text"]) <= 600
        bad = rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "where", "arguments": {"nmae": "x"}}})["result"]
        assert bad["isError"] is True and "unknown argument" in bad["content"][0]["text"]
        assert rpc({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "nope", "arguments": {}}})["error"]["code"] == -32602
        assert rpc({"jsonrpc": "2.0", "id": 6, "method": "nope"})["error"]["code"] == -32601
    finally:
        p.stdin.close(); p.wait(timeout=10); p.stdout.close(); p.stderr.close()


def test_bench_script_small():
    b = os.path.join(os.path.dirname(CI), "bench", "bench_build.py")
    r = subprocess.run([sys.executable, b, "--files", "60"], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "PASS" in r.stdout, r.stdout + r.stderr
