# -*- coding: utf-8 -*-
"""Marqueur des tests qui écrivent dans la base de .env (`-m "not base"` pour les laisser de côté)."""


def pytest_configure(config):
    config.addinivalue_line("markers", "base: test qui lit ou écrit dans la base configurée dans .env")
