"""Issue #99: the real CLI interrupts the dialogue without a trace or a write."""

import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest


def _order(tmp_path, folder):
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    return [sys.executable, "-m", "monl.cli", "init", "--dir", folder], env


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("entry,folder,message", [
    ("3\n1\n", "p1", "Input interrupted"),
    ("3\n2\nMaBoutique\n" + "n\n" * 80, "p2", "Invalid response after 3 attempts"),
])
def test_init_interrupted_in_sous_process(tmp_path, existing, entry, folder, message):
    if existing:
        (tmp_path / folder).mkdir()
    command, env = _order(tmp_path, folder)
    result = subprocess.run(command, input=entry, text=True, capture_output=True,
                              cwd=tmp_path, env=env, timeout=20)
    assert result.returncode == 2
    if folder == "p2":
        assert result.stderr.startswith(message + ": '")
        assert result.stderr.endswith(": nothing was written; rerun `monl init`.\n")
    else:
        assert result.stderr == f"{message}: nothing was written; rerun `monl init`.\n"
    assert "Traceback" not in result.stdout + result.stderr
    assert sorted(p.name for p in tmp_path.iterdir()) == ([folder] if existing else [])
    assert not (tmp_path / folder).exists() or not list((tmp_path / folder).iterdir())


def test_init_ctrl_c_in_sous_process(tmp_path):
    command, env = _order(tmp_path, "p3")
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, cwd=tmp_path, env=env) as process:
        try:
            # Wait for the real input(), without depending on startup speed.
            output = b""
            deadline = time.monotonic() + 20
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while not output.endswith(b"\n> "):
                    remaining = deadline - time.monotonic()
                    assert remaining > 0 and selector.select(remaining), output
                    block = os.read(process.stdout.fileno(), 4096)
                    assert block, output
                    output += block
            process.send_signal(signal.SIGINT)
            stdout, stderr = process.communicate(timeout=20)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
    assert process.returncode == 130
    assert stderr.decode() == "Input interrupted: nothing was written; rerun `monl init`.\n"
    assert b"Traceback" not in output + stdout + stderr
    assert not list(tmp_path.iterdir())
