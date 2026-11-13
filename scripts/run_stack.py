"""Run every GigBid service as a child process (local dev and the single-container Hugging Face deployment).

    python -m scripts.run_stack                 # all services
    python -m scripts.run_stack --only api,worker
Ports: gigsim 8081, portfolio 8101, marketplace 8102, workspace 8103, api $PORT (8000).
"""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time

PY = sys.executable
SERVICES = {name: [PY, "-m", "scripts.serve", name] for name in
            ["gigsim", "portfolio", "marketplace", "workspace", "worker", "api"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(SERVICES))
    a = ap.parse_args()
    procs: dict[str, subprocess.Popen] = {}
    for name in a.only.split(","):
        procs[name] = subprocess.Popen(SERVICES[name])
        time.sleep(0.5)
    print("started:", ", ".join(f"{n}(pid {p.pid})" for n, p in procs.items()), flush=True)

    def stop(*_):
        for p in procs.values():
            p.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    while True:  # restart crashed services (a supervisor in miniature), so one failure doesn't take the app down
        for name, p in list(procs.items()):
            if p.poll() is not None:
                print(f"{name} exited with {p.returncode}; restarting", flush=True)
                time.sleep(2)
                procs[name] = subprocess.Popen(SERVICES[name])
        time.sleep(2)


if __name__ == "__main__":
    main()
