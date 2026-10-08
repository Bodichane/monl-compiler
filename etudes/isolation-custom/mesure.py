"""Exécute le code custom hostile sous chaque isolation et mesure le surcoût.

Usage : python3 mesure.py  (écrit mesures.json à côté)
"""

import json
import os
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent
SCRIPT = ICI / "hostile_abs.py"
CONTEXTE = json.dumps({"titre": "x"})
TOURS = int(os.environ.get("TOURS", "50"))
ENV_HOTE = {"MONL_JWT_SECRET": "ETUDE_JWT_ENV", "PATH": "/usr/bin:/bin"}


def limites():
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (512 << 20, 512 << 20))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))


def en_processus():
    # Référence : l'appel actuel, dans le processus du backend.
    sys.path.insert(0, str(ICI))
    os.environ["MONL_JWT_SECRET"] = "ETUDE_JWT_ENV"
    import hostile_abs

    return lambda: hostile_abs.Publier(json.loads(CONTEXTE))


def commande(argv, **kw):
    def appel():
        r = subprocess.run(argv, input=CONTEXTE, capture_output=True, text=True, timeout=60, **kw)
        if r.returncode:
            raise RuntimeError(r.stderr[-400:])
        return json.loads(r.stdout.strip().splitlines()[-1])

    return appel


def options():
    tmp = tempfile.mkdtemp()
    yield "a. processus actuel (référence)", en_processus()
    yield (
        "b. sous-processus -I, env vide, cwd tmp, RLIMIT",
        commande([sys.executable, "-I", str(SCRIPT)], env={}, cwd=tmp, preexec_fn=limites),
    )
    bwrap = [
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--clearenv",
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/lib",
        "/lib",
        "--symlink",
        "usr/lib64",
        "/lib64",
        "--symlink",
        "usr/bin",
        "/bin",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--ro-bind",
        str(SCRIPT),
        "/sandbox/custom.py",
        "--chdir",
        "/tmp",
    ]
    yield (
        "c. bubblewrap (namespaces, FS vide, pas de réseau)",
        commande(
            bwrap + ["/usr/bin/python3", "-I", "/sandbox/custom.py"], env={}, preexec_fn=limites
        ),
    )
    yield (
        "d. podman --network none --read-only",
        commande(
            [
                "podman",
                "run",
                "--rm",
                "-i",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--entrypoint",
                "python3",
                "-v",
                f"{SCRIPT}:/sandbox/custom.py:ro,Z",
                "localhost/monl-platform:postmerge",
                "-I",
                "/sandbox/custom.py",
            ],
            env={**os.environ, "MONL_JWT_SECRET": ""},
        ),
    )


def main():
    import re
    import socket

    ecoute = socket.socket()
    ecoute.bind(("127.0.0.1", 0))
    ecoute.listen(64)
    port = ecoute.getsockname()[1]
    SCRIPT.write_text(re.sub(r"PORT_HOTE = \d+", f"PORT_HOTE = {port}", SCRIPT.read_text()))
    import threading

    def accepter():
        while True:
            c, _ = ecoute.accept()
            c.close()

    threading.Thread(target=accepter, daemon=True).start()
    resultats = []
    for nom, appel in options():
        tours = TOURS if not nom.startswith("d.") else min(TOURS, 15)
        verdict = appel()
        durees = []
        for _ in range(tours):
            t = time.perf_counter()
            appel()
            durees.append(time.perf_counter() - t)
        reussites = sum(v["ok"] for v in verdict.values())
        ligne = {
            "option": nom,
            "tentatives_reussies": f"{reussites}/{len(verdict)}",
            "detail": {k: v["ok"] for k, v in verdict.items()},
            "mediane_ms": round(statistics.median(durees) * 1000, 2),
            "tours": tours,
        }
        print(json.dumps(ligne, ensure_ascii=False))
        resultats.append(ligne)
    (ICI / "mesures.json").write_text(json.dumps(resultats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
