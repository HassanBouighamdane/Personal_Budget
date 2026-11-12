# -*- coding: utf-8 -*-
"""Modèles Pydantic : validation des entrées de l'API."""

from datetime import date, datetime
from typing import Annotated, List, Literal, Optional
from pydantic import AfterValidator, BaseModel, Field, StringConstraints, model_validator


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
Tags = Annotated[List[str], Field(max_length=50), AfterValidator(_valider_tags)]

# ---------------------------------------------------------------- limites des saisies
# Les espaces autour sont retirés AVANT de vérifier la longueur : un nom fait d'espaces est
# refusé (au lieu d'être enregistré vide), et une saisie ne peut pas remplir la base.
MONTANT_MAX = 1e10          # 10 milliards de DH : bien au-delà de tout montant réel


def Texte(max_length: int, min_length: int = 0):
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)]


Nom = Texte(100, min_length=1)
CodeTitre = Texte(60, min_length=1)
Libelle = Texte(200)
Description = Texte(500)
TexteLong = Texte(5000)
Montant = Annotated[float, Field(gt=0, le=MONTANT_MAX)]              # strictement positif
MontantOuZero = Annotated[float, Field(ge=0, le=MONTANT_MAX)]
Cours = Annotated[float, Field(ge=0, le=10_000_000)]                 # cours d'un titre, en DH
# Mot de passe : jamais modifié (espaces compris), mais borné : PBKDF2 sur un texte énorme coûte cher
MotDePasse = Annotated[str, Field(max_length=200)]


class LoginIn(BaseModel):
    utilisateur: Texte(100)
    mot_de_passe: MotDePasse
    rester_connecte: bool = False   # session de 30 jours au lieu d'un seul

class MdpIn(BaseModel):
    actuel: MotDePasse
    nouveau: str = Field(min_length=6, max_length=200)

class DepenseIn(BaseModel):
    date: DateISO
    categorie: Nom
    description: Description = ""
    montant: Montant
    tags: Tags = []

class RevenuIn(BaseModel):
    date: DateISO
    source: Texte(100) = ""          # vide : revenu sans source
    description: Description = ""
    montant: Montant
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
    nom: Texte(100) = ""
    description: Description = ""
    montant: Montant
    tags: Tags = []

class ImportIn(BaseModel):
    lignes: List[LigneImport] = Field(max_length=5000)
    simulation: bool = False    # true : statut de chaque ligne sans rien enregistrer (aperçu)

class CategorieIn(BaseModel):
    nom: Nom
    budget: MontantOuZero
    fixe: bool = False      # charge fixe (loyer, factures) : hors budget journalier/hebdo
    # Mois (AAAA-MM) à partir duquel le budget et « fixe » s'appliquent ; par défaut le mois en cours.
    # Les mois antérieurs gardent leur budget (cf. budgets_historique).
    a_partir_de: MoisISO = None

class ObjectifIn(BaseModel):
    objectif: MontantOuZero

class NomIn(BaseModel):
    nom: Nom

class SourceIn(BaseModel):
    nom: Nom
    travail: Optional[bool] = None   # revenu du travail (taux horaire) ; None = inchangé

class HeuresTravailIn(BaseModel):
    heures_mois: float = Field(gt=0, le=744)

class ParametresBourse(BaseModel):
    # Fiscalité — taxe sur les profits de cession de valeurs mobilières
    taux_tpcvm: float = Field(ge=0, le=1)


TypeInstrument = Literal["Action", "Obligation", "OPCVM", "IPO"]


class TransactionBourseCreate(BaseModel):
    """Achat/vente : prix déjà net (aucun frais n'est calculé automatiquement,
    saisis directement le prix auquel l'opération a réellement eu lieu)."""
    date_operation: date
    titre: CodeTitre
    isin: Optional[str] = Field(default=None, max_length=20)
    type_instrument: TypeInstrument = "Action"
    type_operation: Literal["Achat", "Vente"]
    quantite: float = Field(gt=0, le=1e9)
    cours_unitaire: Cours
    autres_frais: MontantOuZero = 0   # frais ponctuel éventuel, saisi manuellement
    tpcvm: MontantOuZero = 0          # TPCVM retenue sur une vente, saisie manuellement (ignorée pour un achat)
    note: Texte(2000) = ""            # pourquoi j'ai acheté / vendu


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
    note: str = ""


class PrixMaj(BaseModel):
    cours_actuel: Cours


class TitreBourse(BaseModel):
    id: int
    code: str
    nom: str
    secteur: str
    isin: Optional[str] = None


class CibleSecteur(BaseModel):
    secteur: Nom
    cible: float = Field(ge=0, le=1)      # part du portefeuille, 0,25 = 25 %


class CiblesIn(BaseModel):
    cibles: List[CibleSecteur] = Field(max_length=100)

    @model_validator(mode="after")
    def _total(self):
        if sum(c.cible for c in self.cibles) > 1.0001:
            raise ValueError("La somme des cibles dépasse 100 %")
        if len({c.secteur.strip() for c in self.cibles}) != len(self.cibles):
            raise ValueError("Secteur en double")
        return self


class TitreBourseIn(BaseModel):
    code: CodeTitre
    nom: Nom
    secteur: Texte(100) = ""
    isin: Optional[str] = Field(default=None, max_length=20)      # rapproche le titre du flux de cours automatiques
 
 
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
    # Taux de rendement annuel (TRI) tenant compte de la date des apports ; None avant 3 mois d'historique
    rendement_annualise: Optional[float] = None


# ---------------------------------------------------------------- Dividendes
class DividendeCreate(BaseModel):
    """Montant NET déjà reçu (après retenue à la source) — saisi directement, aucun calcul."""
    date_operation: date
    titre: CodeTitre
    montant: Montant


class DividendeOut(BaseModel):
    id: int
    date_operation: date
    titre: str
    montant: float


# ---------------------------------------------------------------- Frais de compte
class FraisBourseCreate(BaseModel):
    """Frais récurrents ou ponctuels indépendants d'une transaction (ex : abonnement courtier)."""
    date_operation: date
    libelle: Libelle = ""
    montant: Montant


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
    montant: Montant
    libelle: Libelle = ""


class MouvementBourseOut(BaseModel):
    id: int
    date_operation: date
    type_mouvement: str
    montant: float
    libelle: str


# ---------------------------------------------------------------- Lectures
class LivreIn(BaseModel):
    """Livre terminé. Seuls le titre et la date de fin sont obligatoires."""
    titre: Texte(200, min_length=1)
    auteur: Texte(150) = ""
    genre: Texte(100) = ""
    date_debut: Optional[date] = None
    date_fin: date
    pages: Optional[int] = Field(default=None, gt=0, le=100_000)
    note: Optional[int] = Field(default=None, ge=1, le=5)
    commentaire: TexteLong = ""
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
    titre: Texte(200, min_length=1)
    auteur: Texte(150) = ""
    genre: Texte(100) = ""
    pages: Optional[int] = Field(default=None, gt=0, le=100_000)
    isbn: str = Field(default="", max_length=20)
    couverture: str = Field(default="", max_length=500)
    commentaire: TexteLong = ""
    date_debut: Optional[date] = None


class ALireOut(ALireIn):
    id: int
    commentaire: str = ""     # sortie : pas de limite (un ancien commentaire plus long reste lisible)
    nb_notes: int = 0
    # Suivi de la lecture en cours (None tant qu'aucune page n'est notée)
    page_actuelle: Optional[int] = None
    derniere_lecture: Optional[date] = None
    pages_par_jour: Optional[float] = None
    fin_estimee: Optional[date] = None


class ProgressionIn(BaseModel):
    page: int = Field(ge=0, le=100_000)


class PretLivreIn(BaseModel):
    titre: str = Field(min_length=1, max_length=200)
    personne: str = Field(min_length=1, max_length=100)
    date_pret: date
    date_retour: Optional[date] = None
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def _coherence(self):
        self.titre, self.personne = self.titre.strip(), self.personne.strip()
        if not self.titre or not self.personne:
            raise ValueError("Indique le livre et la personne")
        if self.date_retour and self.date_retour < self.date_pret:
            raise ValueError("Le retour ne peut pas précéder le prêt")
        return self


class PretLivreOut(BaseModel):
    id: int
    titre: str
    personne: str
    date_pret: date
    date_retour: Optional[date]
    note: str
    jours: int      # durée du prêt : jusqu'à aujourd'hui, ou jusqu'au retour


class NoteIn(BaseModel):
    """Note ou citation, rattachée à un livre terminé OU à un livre à lire / en cours."""
    livre_id: Optional[int] = None
    a_lire_id: Optional[int] = None
    type: Literal["note", "citation"] = "note"
    texte: Texte(5000, min_length=1)
    page: Optional[int] = Field(default=None, gt=0, le=100_000)

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



class GenreOut(BaseModel):
    id: int
    nom: str


class ObjectifsLecture(BaseModel):
    annuel: int = Field(ge=0, le=10_000)
    mensuel: int = Field(ge=0, le=1_000)


# ---------------------------------------------------------------- Carnet : dettes et prêts
class DetteIn(BaseModel):
    """`pret` : j'ai prêté (on me doit) ; `emprunt` : j'ai emprunté (je dois)."""
    sens: Literal["pret", "emprunt"]
    personne: str = Field(min_length=1, max_length=100)
    montant: Montant
    date_operation: date
    echeance: Optional[date] = None
    libelle: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def _coherence(self):
        self.personne = self.personne.strip()
        if not self.personne:
            raise ValueError("Indique la personne")
        if self.echeance and self.echeance < self.date_operation:
            raise ValueError("L'échéance doit suivre la date du prêt")
        return self


class RemboursementIn(BaseModel):
    date_operation: date
    montant: Montant
    libelle: str = Field(default="", max_length=200)


class RemboursementOut(BaseModel):
    id: int
    date_operation: date
    montant: float
    libelle: str


class DetteOut(BaseModel):
    id: int
    sens: str
    personne: str
    montant: float
    date_operation: date
    echeance: Optional[date]
    libelle: str
    rembourse: float
    reste: float
    remboursements: List[RemboursementOut]


# ---------------------------------------------------------------- Carnet : échéances
class EcheanceIn(BaseModel):
    titre: str = Field(min_length=1, max_length=150)
    categorie: str = Field(default="", max_length=50)
    date_echeance: date
    rappel_jours: int = Field(default=30, ge=0, le=365)
    recurrence_mois: Optional[int] = Field(default=None, gt=0, le=120)
    note: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def _titre_non_vide(self):
        self.titre = self.titre.strip()
        if not self.titre:
            raise ValueError("Indique le titre")
        return self


class EcheanceOut(BaseModel):
    id: int
    titre: str
    categorie: str
    date_echeance: date
    rappel_jours: int
    recurrence_mois: Optional[int]
    note: str
    jours_restants: int      # négatif = en retard
    a_rappeler: bool         # dans la fenêtre de rappel (ou en retard)


# ---------------------------------------------------------------- Objectifs d'épargne par projet
class ProjetIn(BaseModel):
    """Objectif d'épargne nommé (voyage, fonds d'urgence, voiture). `archive` : atteint ou abandonné."""
    nom: str = Field(min_length=1, max_length=100)
    cible: float = Field(gt=0, le=1e10)
    date_limite: Optional[date] = None
    note: str = Field(default="", max_length=1000)
    archive: bool = False

    @model_validator(mode="after")
    def _nom_non_vide(self):
        self.nom = self.nom.strip()
        if not self.nom:
            raise ValueError("Indique le nom de l'objectif")
        self.note = self.note.strip()
        return self


class VersementIn(BaseModel):
    """Argent mis de côté pour un objectif (positif) ou repris (négatif)."""
    date_operation: date
    montant: float = Field(ge=-1e10, le=1e10)
    libelle: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def _non_nul(self):
        if self.montant == 0:
            raise ValueError("Le montant ne peut pas être nul")
        self.libelle = self.libelle.strip()
        return self


class VersementOut(BaseModel):
    id: int
    date_operation: date
    montant: float
    libelle: str


class ProjetOut(BaseModel):
    id: int
    nom: str
    cible: float
    date_limite: Optional[date]
    note: str
    archive: bool
    verse: float                     # total mis de côté
    reste: float                     # ce qui manque (0 une fois atteint)
    progression: float               # verse ÷ cible (ratio, peut dépasser 1)
    atteint: bool
    mois_restants: Optional[int]     # mois jusqu'à la date limite, celui-ci compris (None sans date ou si dépassée)
    par_mois: Optional[float]        # à mettre de côté chaque mois pour tenir la date limite
    en_retard: bool                  # date limite dépassée sans avoir atteint la cible
    versements: List[VersementOut]


# ---------------------------------------------------------------- Patrimoine
class ActifIn(BaseModel):
    """Actif hors Bourse, à valeur saisie à la main."""
    nom: str = Field(min_length=1, max_length=100)
    type: str = Field(default="Autre", max_length=30)
    valeur: MontantOuZero
    verse: MontantOuZero = 0
    zakat: bool = False
    maj_le: date
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def _nom_non_vide(self):
        self.nom = self.nom.strip()
        if not self.nom:
            raise ValueError("Indique le nom")
        return self


class ReglagesPatrimoine(BaseModel):
    solde_depart: float = Field(default=0, ge=-MONTANT_MAX, le=MONTANT_MAX)   # argent détenu avant la première saisie (peut être négatif)
    prix_or_gramme: float = Field(default=0, ge=0, le=100_000)
    debut_hawl: Optional[date] = None       # début de l'année lunaire en cours pour la zakat
    # Liberté financière ; None = inchangé
    taux_retrait: Optional[float] = Field(default=None, gt=0, le=0.2)   # 4 % → objectif = 25 × dépenses annuelles
    rendement: Optional[float] = Field(default=None, ge=-0.1, le=0.3)   # rendement annuel après inflation


class CoursPasseIn(BaseModel):
    titre: CodeTitre
    cours: Optional[float] = Field(default=None, gt=0, le=10_000_000)   # None : retirer le cours saisi


class CoursPassesIn(BaseModel):
    """Cours de fin de mois relevés sur un relevé du courtier, pour la courbe du patrimoine."""
    jour: date
    cours: List[CoursPasseIn] = Field(max_length=200)


class EnvoiIn(BaseModel):
    """Un envoi automatique activé ou coupé sur un canal : la note du jour (avec le message du matin),
    le résumé de la semaine, le bilan du mois ou celui de l'année."""
    envoi: Literal["note", "semaine", "mois", "annee"]
    canal: Literal["telegram", "email"]
    actif: bool
