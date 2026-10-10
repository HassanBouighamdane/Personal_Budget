# -*- coding: utf-8 -*-
"""Modèles Pydantic : validation des entrées de l'API."""

from datetime import date, datetime
from typing import Annotated, List, Literal, Optional
from pydantic import AfterValidator, BaseModel, Field, model_validator


def _valider_date_iso(v: str) -> str:
    """Exige une vraie date au format AAAA-MM-JJ (ex : refuse 2026-02-30 ou 18/09/2026).
    La valeur reste une chaîne, stockée telle quelle : les requêtes du Budget filtrent
    les dates en texte (`date LIKE '2026-09-%'`, `substr(date,1,7)`)."""
    try:
        if datetime.strptime(v, "%Y-%m-%d").strftime("%Y-%m-%d") != v:
            raise ValueError
    except ValueError:
        raise ValueError("Date attendue au format AAAA-MM-JJ")
    return v


# Date du module Budget : chaîne validée (et non `date`, pour garder un stockage texte identique)
DateISO = Annotated[str, AfterValidator(_valider_date_iso)]


def _valider_mois(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    try:
        if datetime.strptime(v, "%Y-%m").strftime("%Y-%m") != v:
            raise ValueError
    except ValueError:
        raise ValueError("Mois attendu au format AAAA-MM")
    return v


def _valider_tags(v: List[str]) -> List[str]:
    """Tags en minuscules, espaces normalisés, sans doublon ; 10 au plus, 40 caractères chacun."""
    tags = []
    for t in v:
        t = " ".join(t.split()).lower().lstrip("#")[:40]
        if t and t not in tags:
            tags.append(t)
    if len(tags) > 10:
        raise ValueError("10 tags au maximum")
    return tags


MoisISO = Annotated[Optional[str], AfterValidator(_valider_mois)]
Tags = Annotated[List[str], AfterValidator(_valider_tags)]


class LoginIn(BaseModel):
    utilisateur: str
    mot_de_passe: str

class MdpIn(BaseModel):
    actuel: str
    nouveau: str = Field(min_length=6)

class DepenseIn(BaseModel):
    date: DateISO
    categorie: str
    description: str = ""
    montant: float = Field(gt=0)
    tags: Tags = []

class RevenuIn(BaseModel):
    date: DateISO
    source: str = ""
    description: str = ""
    montant: float = Field(gt=0)
    tags: Tags = []

class DepenseRestauree(DepenseIn):
    """Dépense supprimée remise en place (« Annuler ») sous son identifiant d'origine."""
    id: int

class RevenuRestaure(RevenuIn):
    id: int

class LigneImport(BaseModel):
    """Ligne d'un relevé importé : `nom` = catégorie (dépense) ou source (revenu)."""
    type: Literal["depense", "revenu"]
    date: DateISO
    nom: str = ""
    description: str = ""
    montant: float = Field(gt=0)
    tags: Tags = []

class ImportIn(BaseModel):
    lignes: List[LigneImport] = Field(max_length=5000)
    simulation: bool = False    # true : statut de chaque ligne sans rien enregistrer (aperçu)

class CategorieIn(BaseModel):
    nom: str = Field(min_length=1)
    budget: float = Field(ge=0)
    fixe: bool = False      # charge fixe (loyer, factures) : hors budget journalier/hebdo
    # Mois (AAAA-MM) à partir duquel le budget et « fixe » s'appliquent ; par défaut le mois en cours.
    # Les mois antérieurs gardent leur budget (cf. budgets_historique).
    a_partir_de: MoisISO = None

class ObjectifIn(BaseModel):
    objectif: float = Field(ge=0)

class NomIn(BaseModel):
    nom: str = Field(min_length=1)

class ParametresBourse(BaseModel):
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
    tpcvm: float = Field(default=0, ge=0)          # TPCVM retenue sur une vente, saisie manuellement (ignorée pour un achat)


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
    tpcvm: float
    montant_net: float


class PrixMaj(BaseModel):
    cours_actuel: float = Field(ge=0)


class TitreBourse(BaseModel):
    id: int
    code: str
    nom: str
    secteur: str
    isin: Optional[str] = None


class CibleSecteur(BaseModel):
    secteur: str = Field(min_length=1, max_length=100)
    cible: float = Field(ge=0, le=1)      # part du portefeuille, 0,25 = 25 %


class CiblesIn(BaseModel):
    cibles: List[CibleSecteur]

    @model_validator(mode="after")
    def _total(self):
        if sum(c.cible for c in self.cibles) > 1.0001:
            raise ValueError("La somme des cibles dépasse 100 %")
        if len({c.secteur.strip() for c in self.cibles}) != len(self.cibles):
            raise ValueError("Secteur en double")
        return self


class TitreBourseIn(BaseModel):
    code: str = Field(min_length=1)
    nom: str = Field(min_length=1)
    secteur: str = ""
    isin: Optional[str] = None      # rapproche le titre du flux de cours automatiques
 
 
class PositionBourse(BaseModel):
    titre: str
    secteur: str
    quantite_achetee: float
    quantite_vendue: float
    quantite_detenue: float
    pru: float
    cours_actuel: float
    valeur_comptable: float
    valeur_marche: float
    plus_value_latente: float
    performance_latente: float
    isin: Optional[str] = None
    cours_manuel: bool = False              # cours saisi à la main : verrouillé jusqu'à remise en automatique
    cours_maj_le: Optional[datetime] = None
    # Dividendes nets reçus sur les 12 derniers mois, rapportés au coût et à la valeur de marché
    dividendes_12m: float = 0
    rendement_cout: float = 0
    rendement_marche: float = 0


class CoursActualisation(BaseModel):
    """Résultat d'une récupération des cours. `etat` : maj (cours écrits), recent (déjà faite
    il y a moins de 15 min), rien (aucun titre détenu à mettre à jour), erreur (sources injoignables)."""
    etat: Literal["maj", "recent", "rien", "erreur"]
    nb_maj: int = 0
    introuvables: List[str] = []            # titres détenus absents de la source de cours
    message: str = ""
 
 
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
    # Mouvements banque ↔ compte Bourse sur la période sélectionnée
    apports_periode: float
    retraits_periode: float
    # Compte Bourse dans son ensemble — toujours calculé sur tout l'historique
    especes_disponibles: float      # argent sur le compte, non investi en titres
    apports_nets: float             # apports − retraits (argent réellement sorti de ta poche)
    patrimoine_total: float         # valeur de marché des titres + espèces disponibles
    performance_globale: float      # patrimoine − apports nets (en DH)
    performance_globale_pct: float  # ratio, affiché en % par le frontend


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

# ---------------------------------------------------------------- Mouvements banque ↔ compte Bourse
class MouvementBourseCreate(BaseModel):
    """Apport (banque → compte Bourse) ou retrait (compte Bourse → banque) : un transfert,
    ni une dépense ni un revenu du Budget."""
    date_operation: date
    type_mouvement: Literal["Apport", "Retrait"]
    montant: float = Field(gt=0)
    libelle: str = ""


class MouvementBourseOut(BaseModel):
    id: int
    date_operation: date
    type_mouvement: str
    montant: float
    libelle: str


# ---------------------------------------------------------------- Lectures
class LivreIn(BaseModel):
    """Livre terminé. Seuls le titre et la date de fin sont obligatoires."""
    titre: str = Field(min_length=1, max_length=200)
    auteur: str = Field(default="", max_length=150)
    genre: str = Field(default="", max_length=100)
    date_debut: Optional[date] = None
    date_fin: date
    pages: Optional[int] = Field(default=None, gt=0)
    note: Optional[int] = Field(default=None, ge=1, le=5)
    commentaire: str = ""
    isbn: str = Field(default="", max_length=20)
    couverture: str = Field(default="", max_length=500)    # URL de l'image (Open Library)

    @model_validator(mode="after")
    def _dates_coherentes(self):
        if self.date_debut and self.date_debut > self.date_fin:
            raise ValueError("La date de début doit précéder la date de fin")
        return self


class LivreOut(BaseModel):
    id: int
    titre: str
    auteur: str
    genre: str
    date_debut: Optional[date]
    date_fin: date
    pages: Optional[int]
    note: Optional[int]
    commentaire: str
    isbn: str = ""
    couverture: str = ""
    nb_notes: int = 0


class ALireIn(BaseModel):
    """Livre à lire ; `date_debut` renseignée = en cours de lecture."""
    titre: str = Field(min_length=1, max_length=200)
    auteur: str = Field(default="", max_length=150)
    genre: str = Field(default="", max_length=100)
    pages: Optional[int] = Field(default=None, gt=0)
    isbn: str = Field(default="", max_length=20)
    couverture: str = Field(default="", max_length=500)
    commentaire: str = ""
    date_debut: Optional[date] = None


class ALireOut(ALireIn):
    id: int
    nb_notes: int = 0


class NoteIn(BaseModel):
    """Note ou citation, rattachée à un livre terminé OU à un livre à lire / en cours."""
    livre_id: Optional[int] = None
    a_lire_id: Optional[int] = None
    type: Literal["note", "citation"] = "note"
    texte: str = Field(min_length=1, max_length=5000)
    page: Optional[int] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _un_seul_livre(self):
        if (self.livre_id is None) == (self.a_lire_id is None):
            raise ValueError("Indique soit livre_id, soit a_lire_id")
        return self


class NoteOut(BaseModel):
    id: int
    livre_id: Optional[int]
    a_lire_id: Optional[int]
    type: str
    texte: str
    page: Optional[int]


class FicheIsbn(BaseModel):
    isbn: str
    titre: str
    auteur: str
    pages: Optional[int]
    couverture: str


class GenreOut(BaseModel):
    id: int
    nom: str


class ObjectifsLecture(BaseModel):
    annuel: int = Field(ge=0)
    mensuel: int = Field(ge=0)
