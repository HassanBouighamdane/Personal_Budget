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
    # Droits de garde — frais trimestriels sur encours, indépendants des transactions
    taux_droit_garde_annuel: float = Field(ge=0, le=1)
    droit_garde_min_trimestriel: float = Field(ge=0)
    # Fiscalité — taxe sur les profits de cession de valeurs mobilières
    taux_tpcvm: float = Field(ge=0, le=1)


TypeInstrument = Literal["Action", "Obligation", "OPCVM", "IPO"]


class TransactionBourseCreate(BaseModel):
    """Achat/vente : prix déjà net (aucun frais n'est calculé automatiquement,
    saisis directement le prix auquel l'opération a réellement eu lieu)."""
    date_operation: date
    titre: str
    isin: Optional[str] = None
    type_instrument: TypeInstrument = "Action"
    type_operation: Literal["Achat", "Vente"]
    quantite: float = Field(gt=0)
    cours_unitaire: float = Field(ge=0)
    autres_frais: float = Field(default=0, ge=0)   # frais ponctuel éventuel, saisi manuellement


# Schéma de la partie Bourse pour l'API (sortie)
class TransactionBourseOut(BaseModel):
    id: int
    date_operation: date
    titre: str
    isin: Optional[str]
    type_instrument: str
    type_operation: str
    quantite: float
    cours_unitaire: float
    montant_brut: float
    autres_frais: float
    total_frais: float
    montant_net: float


class PrixMaj(BaseModel):
    cours_actuel: float = Field(ge=0)


class DroitsGarde(BaseModel):
    base_calcul: float
    taux_annuel: float
    montant_trimestriel_estime: float
    minimum_trimestriel: float
    montant_trimestriel_du: float


class TitreBourse(BaseModel):
    code: str
    nom: str
    secteur: str
 
 
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
    type_instrument: str
    quantite: float
    cours_vente: float
    pru: float
    montant_net: float
    gain_brut: float
    taux_tpcvm: float
    tpcvm: float
    gain_net: float
 
 
class DashboardBourse(BaseModel):
    # Portefeuille actuel — indépendant de la période sélectionnée (pas d'historique de cours)
    cout_acquisition: float
    valeur_marche: float
    plus_value_latente: float
    performance_latente: float
    # Flux de la période sélectionnée (mois/année choisis, ou tout l'historique si aucun filtre)
    gains_bruts_realises: float
    tpcvm_total: float
    gains_nets_realises: float
    dividendes_nets: float
    frais_transactions_totaux: float
    frais_compte_totaux: float
    resultat_net_periode: float
    # Indicatif, toujours calculé sur l'encours actuel
    droits_garde_trimestriel_estime: float


# ---------------------------------------------------------------- Dividendes
class DividendeCreate(BaseModel):
    """Montant NET déjà reçu (après retenue à la source) — saisi directement, aucun calcul."""
    date_operation: date
    titre: str
    montant: float = Field(gt=0)


class DividendeOut(BaseModel):
    id: int
    date_operation: date
    titre: str
    montant: float


# ---------------------------------------------------------------- Frais de compte
class FraisBourseCreate(BaseModel):
    """Frais récurrents ou ponctuels indépendants d'une transaction (ex : abonnement courtier)."""
    date_operation: date
    libelle: str = ""
    montant: float = Field(gt=0)


class FraisBourseOut(BaseModel):
    id: int
    date_operation: date
    libelle: str
    montant: float