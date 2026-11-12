# -*- coding: utf-8 -*-
"""
Construit le frontend React : `npm ci` puis `npm run build` dans frontend-react/, qui produit
frontend-react/dist/ (servi par FastAPI, cf. config.FRONT_DIR).

- Sur Vercel : lancé à chaque déploiement, après l'installation des paquets Python
  ([tool.vercel.scripts] build, dans pyproject.toml). dist/ n'est donc plus versionné.
- En local : lancer_budget.bat / .sh l'appellent si dist/ manque. Sinon, après une modification
  du frontend : `cd frontend-react && npm run build` (plus rapide, sans réinstaller node_modules).

Usage : python backend/construire_frontend.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

FRONT = Path(__file__).resolve().parent.parent / "frontend-react"


def main() -> int:
    npm = shutil.which("npm")
    if not npm:
        print("npm introuvable : installe Node.js (https://nodejs.org) pour construire le frontend.", file=sys.stderr)
        return 1
    # --include=dev : TypeScript et Vite sont des dépendances de développement, que npm omettrait
    # si NODE_ENV=production (cas possible sur un serveur de build)
    for etape in (["ci", "--include=dev", "--no-audit", "--no-fund"], ["run", "build"]):
        print(f"[frontend] npm {' '.join(etape)}", flush=True)
        if subprocess.run([npm, *etape], cwd=FRONT).returncode != 0:
            print(f"[frontend] échec de « npm {etape[0]} »", file=sys.stderr)
            return 1
    if not (FRONT / "dist" / "index.html").exists():
        print("[frontend] build terminé sans dist/index.html", file=sys.stderr)
        return 1
    print("[frontend] dist/ prêt", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
