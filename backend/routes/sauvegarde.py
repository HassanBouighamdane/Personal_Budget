# -*- coding: utf-8 -*-
"""Téléchargement de la sauvegarde complète (toutes les tables, cf. sauvegarde.py)."""
from fastapi import APIRouter, Depends, Response

import sauvegarde
from config import aujourdhui
from securite import utilisateur_courant

router = APIRouter(prefix="/api", tags=["sauvegarde"], dependencies=[Depends(utilisateur_courant)])


@router.get("/sauvegarde")
def telecharger_sauvegarde():
    """Fichier JSON lisible, à garder hors de l'hébergeur ; se restaure avec scripts/restaurer_sauvegarde.py."""
    nom = f"carnet-{aujourdhui().isoformat()}.json"
    return Response(sauvegarde.en_json(sauvegarde.exporter()), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{nom}"'})
