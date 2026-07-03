#!/bin/bash
cd "$(dirname "$0")"
xdg-open http://localhost:8500 &
.venv/bin/python backend/app.py