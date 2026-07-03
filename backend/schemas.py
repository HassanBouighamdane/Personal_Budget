# -*- coding: utf-8 -*-
"""Modèles Pydantic : validation des entrées de l'API."""
from pydantic import BaseModel, Field

class LoginIn(BaseModel):
    utilisateur: str
    mot_de_passe: str

class MdpIn(BaseModel):
    actuel: str
    nouveau: str = Field(min_length=6)

class DepenseIn(BaseModel):
    date: str
    categorie: str
    description: str = ""
    montant: float = Field(gt=0)
    paiement: str = ""

class RevenuIn(BaseModel):
    date: str
    source: str = ""
    montant: float = Field(gt=0)

class CategorieIn(BaseModel):
    nom: str = Field(min_length=1)
    budget: float = Field(ge=0)

class ObjectifIn(BaseModel):
    objectif: float = Field(ge=0)

class NomIn(BaseModel):
    nom: str = Field(min_length=1)