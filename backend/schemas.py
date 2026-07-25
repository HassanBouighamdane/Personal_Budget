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
    # Actions cotées (commission de courtage + règlement/livraison + impôt de bourse + TVA sur courtage uniquement)
    taux_courtage_action: float = Field(ge=0, le=1)
    taux_reglement_livraison: float = Field(ge=0, le=1)
    taux_impot_bourse_action: float = Field(ge=0, le=1)
    taux_tva: float = Field(ge=0, le=1)
    # Obligations cotées (commission fixe + impôt de bourse réduit, pas de courtage ni de TVA)
    commission_fixe_obligation: float = Field(ge=0)
    taux_impot_bourse_obligation: float = Field(ge=0, le=1)
    # Droits de garde — frais trimestriels sur encours, indépendants des transactions
    taux_droit_garde_annuel: float = Field(ge=0, le=1)
    droit_garde_min_trimestriel: float = Field(ge=0)
    # IPO / souscriptions (introduction en bourse, augmentation de capital)
    taux_souscription_ipo: float = Field(ge=0, le=1)
    min_souscription_ipo: float = Field(ge=0)
    # OPCVM — taux par défaut ; varient fortement par fonds, à ajuster à la saisie si besoin
    droits_entree_opcvm_defaut: float = Field(ge=0, le=1)
    droits_sortie_opcvm_defaut: float = Field(ge=0, le=1)
    # Fiscalité
    taux_tpcvm: float = Field(ge=0, le=1)


TypeInstrument = Literal["Action", "Obligation", "OPCVM", "IPO"]
StructureIPO = Literal["souscription", "action"]


class TransactionBourseCreate(BaseModel):
    date_operation: date
    titre: str
    isin: Optional[str] = None
    type_instrument: TypeInstrument = "Action"
    type_operation: Literal["Achat", "Vente"]
    quantite: float = Field(gt=0)
    cours_unitaire: float = Field(ge=0)
    autres_frais: float = Field(default=0, ge=0)
    # IPO uniquement : quelle structure de frais appliquer
    structure_ipo: StructureIPO = "souscription"
    # Surcharges optionnelles : si absentes, les taux courants des Paramètres sont utilisés
    taux_courtage: Optional[float] = None             # Action, ou IPO si structure_ipo="action"
    taux_reglement_livraison: Optional[float] = None  # Action, ou IPO si structure_ipo="action"
    taux_impot_bourse: Optional[float] = None         # Action, Obligation, ou IPO si structure_ipo="action"
    taux_tva: Optional[float] = None                  # Action, ou IPO si structure_ipo="action"
    commission_fixe: Optional[float] = None           # Obligation
    taux_droits_opcvm: Optional[float] = None         # OPCVM (entrée ou sortie selon type_operation)
    taux_souscription: Optional[float] = None         # IPO si structure_ipo="souscription"
    min_souscription: Optional[float] = None          # IPO si structure_ipo="souscription"


# Schéma de la partie Bourse pour l'API (sortie)
class TransactionBourseOut(BaseModel):
    id: int
    date_operation: date
    titre: str
    isin: Optional[str]
    type_instrument: str
    structure_ipo: Optional[str] = None
    type_operation: str
    quantite: float
    cours_unitaire: float
    montant_brut: float
    detail_frais: dict          # ex Action: {"courtage":.., "reglement_livraison":.., "impot_bourse":.., "tva":..}
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
    droits_garde_trimestriel_estime: float
    resultat_net_global: float