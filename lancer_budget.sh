#!/bin/bash
cd "$(dirname "$0")"
# Frontend pas encore construit (dist/ n'est pas versionné) : npm ci + npm run build
if [ ! -f frontend-react/dist/index.html ]; then
  .venv/bin/python backend/construire_frontend.py || exit 1
fi
xdg-open http://localhost:8500 &
.venv/bin/python backend/app.py
