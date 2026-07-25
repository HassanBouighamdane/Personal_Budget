# -*- coding: utf-8 -*-
"""Modèles Pydantic : validation des entrées de l'API."""

from datetime import date
from typing import Literal, Optional
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

class ParametresBourse(BaseModel):
    taux_commission: float = Field(ge=0, le=1)
    taux_tva: float = Field(ge=0, le=1)
    taux_tpcvm: float = Field(ge=0, le=1)
 
 
class TransactionBourseCreate(BaseModel):
    date_operation: date
    titre: str
    isin: Optional[str] = None
    type_operation: Literal["Achat", "Vente"]
    quantite: float = Field(gt=0)
    cours_unitaire: float = Field(ge=0)
    autres_frais: float = Field(default=0, ge=0)
    # taux_commission / taux_tva optionnels : si absents, on prend les paramètres courants
    taux_commission: Optional[float] = None
    taux_tva: Optional[float] = None
 
#Schéma de la partie Bourse pour l'API (sortie)
class TransactionBourseOut(BaseModel):
    id: int
    date_operation: date
    titre: str
    isin: Optional[str]
    type_operation: str
    quantite: float
    cours_unitaire: float
    taux_commission: float
    taux_tva: float
    autres_frais: float
    montant_brut: float
    commission: float
    tva_commission: float
    total_frais: float
    montant_net: float
 
 
class PrixMaj(BaseModel):
    cours_actuel: float = Field(ge=0)
 
 
class PositionBourse(BaseModel):
    titre: str
    quantite_achetee: float
    quantite_vendue: float
    quantite_detenue: float
    pru: float
    cours_actuel: float
    valeur_comptable: float
    valeur_marche: float
    plus_value_latente: float
    performance_latente: float
 
 
class GainRealise(BaseModel):
    id: int
    date_operation: date
    titre: str
    quantite: float
    cours_vente: float
    pru: float
    montant_net: float
    gain_brut: float
    taux_tpcvm: float
    tpcvm: float
    gain_net: float
 
 
class DashboardBourse(BaseModel):
    cout_acquisition: float
    valeur_marche: float
    plus_value_latente: float
    performance_latente: float
    gains_bruts_realises: float
    tpcvm_total: float
    gains_nets_realises: float
    commissions_totales: float
    tva_totale: float
    frais_totaux: float
    resultat_net_global: float
 