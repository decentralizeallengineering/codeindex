import os, subprocess, sys

CI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "codeindex")


def ci(repo, *args):
    env = {**os.environ, "CODEINDEX_NO_GRAPH": "1", "CODEINDEX_ROOT": str(repo)}
    return subprocess.run([sys.executable, CI, *args], cwd=repo, capture_output=True, text=True, env=env, timeout=60)


def test_help():
    r = subprocess.run([sys.executable, CI, "--help"], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and "codeindex build" in r.stdout


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
