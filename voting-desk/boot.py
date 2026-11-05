"""Run in the project's own environment, so plain `python app.py` works on a clean machine.

Setup runs as its own process. Claude stops a server that is slow to start, and setup must survive that,
so the next session connects at once.
"""
import os
import shutil
import subprocess
import sys
import time
import venv
from pathlib import Path

ROOT = Path(__file__).parent
ENV = ROOT / ".venv"
PYTHON = ENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
READY = ROOT / ".installed"
LOCK = ROOT / ".installing"


def install():
    uv = shutil.which("uv")
    steps = ([[uv, "venv", ENV], [uv, "pip", "install", "--no-cache", "--python", PYTHON, "-r", ROOT / "requirements.txt"]] if uv else
             [[PYTHON, "-m", "pip", "install", "-q", "--no-cache-dir", "--disable-pip-version-check", "-r", ROOT / "requirements.txt"]])
    if not uv:
        venv.create(ENV, with_pip=True, clear=True)
    with (ROOT / ".install.log").open("w") as log:
        for step in steps:
            subprocess.run(step, check=True, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
    READY.write_text("ok")
    LOCK.unlink(missing_ok=True)


def detach():
    """Start setup so that stopping this process cannot stop it."""
    me = str(Path(__file__).resolve())
    quiet = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name != "nt":
        subprocess.Popen([sys.executable, me], start_new_session=True, **quiet)
        return
    try:
        subprocess.Popen([sys.executable, me], creationflags=0x00000008 | 0x00000200 | 0x01000000, **quiet)
    except OSError:  # no job breakaway here, so go through a helper that exits at once
        subprocess.Popen(["cmd", "/c", "start", "", "/b", sys.executable, me], creationflags=0x08000000, **quiet)


if __name__ == "__main__":
    install()
elif Path(sys.prefix).resolve() != ENV.resolve():
    if not READY.exists():
        print("First run: installing, up to two minutes.", file=sys.stderr, flush=True)
        if not LOCK.exists() or time.time() - LOCK.stat().st_mtime > 600:
            LOCK.write_text("running")
            detach()
        while not READY.exists():
            time.sleep(1)
    sys.exit(subprocess.run([PYTHON, *sys.argv]).returncode)
