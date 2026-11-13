# -*- coding: utf-8 -*-
"""
Saisie rapide par Telegram : on écrit au bot, il enregistre la dépense.

    45 café                  dépense de 45 DH, catégorie devinée (« Restaurants & Cafés »)
    1200 courses #turquie    avec un tag
    café 45 hier             montant à la fin, et daté d'hier (« avant-hier » aussi)
    +8000 salaire            un revenu
    ?                        ce qu'il reste à dépenser aujourd'hui et ce mois-ci
    solde                    les liquidités calculées ; « solde 12500 » note un pointage
    aide                     ce mode d'emploi

Le bot répond par une confirmation avec un bouton « Annuler » et un bouton pour changer de
catégorie. Quand la catégorie ne se devine pas, il propose les catégories en boutons.

Telegram appelle POST /api/telegram/webhook (déclaré par le bouton des Paramètres, setWebhook) :
la route vérifie le secret envoyé dans l'en-tête X-Telegram-Bot-Api-Secret-Token et n'accepte que
les messages de la conversation TELEGRAM_CHAT_ID. Elle répond toujours 200, sinon Telegram renvoie
le même message en boucle ; chaque message n'est traité qu'une fois (telegram_messages).
"""
import json
import re
import secrets
import unicodedata
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_WEBHOOK_SECRET, aujourdhui
from database import db
from messagerie import appel_telegram
from schemas import MONTANT_MAX
from securite import utilisateur_courant

# Sans session : appelé par Telegram, protégé par le secret
webhook = APIRouter(prefix="/api/telegram", tags=["telegram"])
router = APIRouter(prefix="/api/telegram", tags=["telegram"], dependencies=[Depends(utilisateur_courant)])

CHEMIN_WEBHOOK = "/api/telegram/webhook"
DESCRIPTION = "Saisie Telegram"
GARDE_JOURS = 7          # messages déjà traités gardés une semaine (Telegram renvoie au plus 24 h)
MOTS_MIN = 3             # un mot de moins de 3 lettres ne sert pas à deviner la catégorie

AIDE = """Écris-moi tes dépenses, je les enregistre :
• 45 café
• 1200 courses #maison
• café 45 hier
• +8000 salaire (un revenu)

Et aussi :
• ? : ce qu'il te reste à dépenser
• solde : tes liquidités ; « solde 12500 » pour pointer ton solde réel
• aide : ce message"""


def dh(v) -> str:
    """Montant en DH, avec les centimes s'il en a (« 5,50 DH », « 1 200 DH ») : la réponse doit
    montrer exactement ce qui est enregistré (resume_rendu.dh arrondit au dirham, pour les résumés)."""
    v = float(v)
    texte = f"{abs(v):,.0f}" if abs(v - round(v)) < 0.005 else f"{abs(v):,.2f}"
    return ("−" if v < 0 else "") + texte.replace(",", " ").replace(".", ",") + " DH"


def configure() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


# ---------------------------------------------------------------- lecture d'un message
MONTANT = re.compile(r"^(\+)?(\d+(?:[.,]\d{1,2})?)(?:dh|mad)?$", re.I)
DATES = {"hier": 1, "avant-hier": 2}


def sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte.lower()) if unicodedata.category(c) != "Mn")


def analyser(texte: str) -> dict:
    """Message → {"commande": "aide" | "reste" | "solde" | "operation" | None, ...}.
    Opération : {"type": "depense" | "revenu", "montant", "texte", "tags", "jours"} (`jours` :
    0 aujourd'hui, 1 hier...). `commande` None : message incompris (pas de montant)."""
    brut = " ".join(texte.split())
    t = sans_accents(brut).lstrip("/")
    if t in ("", "start", "aide", "help", "?aide"):
        return {"commande": "aide"}
    if t in ("?", "reste", "budget"):
        return {"commande": "reste"}
    if t == "solde" or t.startswith("solde "):
        reste = brut.split(" ", 1)[1] if " " in brut else ""
        m = MONTANT.match(reste.replace(" ", "").replace(" ", "")) if reste else None
        if reste and not m:
            return {"commande": None}
        return {"commande": "solde", "montant": float(m.group(2).replace(",", ".")) if m else None}

    mots = brut.split(" ")
    revenu = mots[0] == "+"
    if revenu:
        mots.pop(0)
    # « hier », « avant-hier » ou « avant hier », n'importe où dans le message
    jours, bas = 0, [sans_accents(m) for m in mots]
    for i in range(len(bas)):
        if bas[i] == "avant" and i + 1 < len(bas) and bas[i + 1] == "hier":
            jours = 2
            del mots[i:i + 2]
            break
        if bas[i] in DATES:
            jours = DATES[bas[i]]
            del mots[i]
            break
    position = next((i for i in (0, len(mots) - 1) if mots and MONTANT.match(mots[i])), None)
    if position is None:
        return {"commande": None}
    m = MONTANT.match(mots.pop(position))
    montant = float(m.group(2).replace(",", "."))
    if not 0 < montant <= MONTANT_MAX:
        return {"commande": None}
    revenu = revenu or bool(m.group(1))
    tags = [w[1:].lower()[:40] for w in mots if w.startswith("#") and len(w) > 1]
    texte_libre = " ".join(w for w in mots if not w.startswith("#")).strip()
    return {"commande": "operation", "type": "revenu" if revenu else "depense", "montant": round(montant, 2),
            "texte": texte_libre[:500], "tags": list(dict.fromkeys(tags))[:10], "jours": jours}


def _mots(texte: str) -> list:
    return [m for m in re.split(r"[^a-z0-9]+", sans_accents(texte)) if len(m) >= MOTS_MIN]


def _correspond(nom: str, mots: list) -> int:
    """Mots du message retrouvés dans le nom (« café » dans « Restaurants & Cafés »)."""
    nom_mots = _mots(nom)
    return sum(1 for m in mots if any(n.startswith(m) or m.startswith(n) for n in nom_mots))


def deviner_categorie(c, texte: str) -> Optional[str]:
    """Catégorie active pour la description `texte` : celle le plus souvent utilisée pour cette même
    description, sinon celle dont le nom contient un mot du message, sinon celle des descriptions
    passées qui contiennent un de ses mots. None : on demandera."""
    actives = [r["nom"] for r in c.execute("SELECT nom FROM categories WHERE actif=1 ORDER BY nom").fetchall()]
    if not texte.strip() or not actives:
        return None
    r = c.execute("""SELECT categorie FROM depenses WHERE lower(trim(description)) = lower(%s) AND categorie = ANY(%s)
                     GROUP BY categorie ORDER BY COUNT(*) DESC, MAX(date) DESC LIMIT 1""", (texte.strip(), actives)).fetchone()
    if r:
        return r["categorie"]
    mots = _mots(texte)
    if not mots:
        return None
    scores = sorted(((_correspond(nom, mots), nom) for nom in actives), key=lambda x: -x[0])
    if scores[0][0] > 0:
        return scores[0][1]
    # Ici avec les accents : la base compare le texte tel qu'il a été saisi (« café »)
    for mot in [m for m in re.split(r"\W+", texte.lower()) if len(m) >= MOTS_MIN]:
        r = c.execute("""SELECT categorie FROM depenses WHERE description ILIKE %s AND categorie = ANY(%s)
                         GROUP BY categorie ORDER BY COUNT(*) DESC, MAX(date) DESC LIMIT 1""",
                      (f"%{mot}%", actives)).fetchone()
        if r:
            return r["categorie"]
    return None


def deviner_source(c, texte: str) -> Optional[str]:
    actives = [r["nom"] for r in c.execute("SELECT nom FROM sources_revenus WHERE actif=1 ORDER BY nom").fetchall()]
    mots = _mots(texte)
    if not mots:
        return None
    scores = sorted(((_correspond(nom, mots), nom) for nom in actives), key=lambda x: -x[0])
    if scores and scores[0][0] > 0:
        return scores[0][1]
    r = c.execute("""SELECT source FROM revenus WHERE lower(trim(description)) = lower(%s) AND source = ANY(%s)
                     GROUP BY source ORDER BY COUNT(*) DESC LIMIT 1""", (texte.strip(), actives)).fetchone()
    return r["source"] if r else None


# ---------------------------------------------------------------- réponses
def _quand(jour: date, auj: date) -> str:
    return {0: "aujourd'hui", 1: "hier", 2: "avant-hier"}.get((auj - jour).days, jour.strftime("%d/%m"))


def _boutons(lignes: list) -> dict:
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in ligne] for ligne in lignes]}


def _clavier_categories(c, prefixe: str, actuelle: Optional[str] = None) -> dict:
    cats = c.execute("SELECT id, nom FROM categories WHERE actif=1 ORDER BY nom").fetchall()
    boutons = [((("✓ " if r["nom"] == actuelle else "") + r["nom"])[:40], f"{prefixe}:{r['id']}") for r in cats]
    return _boutons([boutons[i:i + 2] for i in range(0, len(boutons), 2)] + [[("Abandonner", "x")]])


def _confirmation_depense(c, d: dict, auj: date) -> tuple:
    """(texte, boutons) après l'enregistrement de la dépense `d` (ligne de la base)."""
    from routes.rapports import _categories   # import local : rapports n'a pas à charger ce module
    jour = date.fromisoformat(d["date"])
    mois = d["date"][:7]
    budget = next((x["budget"] for x in _categories(c, mois) if x["nom"] == d["categorie"]), 0)
    depense = c.execute("SELECT COALESCE(SUM(montant),0) t FROM depenses WHERE categorie=%s AND date LIKE %s",
                        (d["categorie"], mois + "-%")).fetchone()["t"]
    lignes = [f"✓ {dh(d['montant'])} · {d['categorie']}",
              " · ".join(x for x in (f"« {d['description']} »" if d["description"] and d["description"] != DESCRIPTION else "",
                                     _quand(jour, auj), " ".join("#" + t for t in d["tags"])) if x)]
    if budget:
        reste = budget - depense
        lignes.append(f"Reste {dh(reste)} sur {d['categorie']} ce mois-ci" if reste >= 0
                      else f"⚠️ {d['categorie']} : budget dépassé de {dh(-reste)} ce mois-ci")
    else:
        lignes.append(f"{dh(depense)} en {d['categorie']} ce mois-ci")
    return "\n".join(lignes), _boutons([[("↩️ Annuler", f"a:d:{d['id']}"), ("🏷️ Catégorie", f"k:{d['id']}")]])


def _inserer_depense(c, op: dict, categorie: str, auj: date) -> dict:
    jour = auj - timedelta(days=op["jours"])
    return c.execute("""INSERT INTO depenses(date,categorie,description,montant,tags) VALUES(%s,%s,%s,%s,%s)
                        RETURNING id, date, categorie, description, montant, tags""",
                     (jour.isoformat(), categorie, op["texte"] or DESCRIPTION, op["montant"], op["tags"])).fetchone()


def operation(c, update_id: int, op: dict, auj: date) -> tuple:
    """Enregistre l'opération lue dans un message ; (texte, boutons) de la réponse."""
    if op["type"] == "revenu":
        source = deviner_source(c, op["texte"])
        jour = auj - timedelta(days=op["jours"])
        r = c.execute("""INSERT INTO revenus(date,source,description,montant,tags) VALUES(%s,%s,%s,%s,%s)
                         RETURNING id""", (jour.isoformat(), source, op["texte"] or DESCRIPTION, op["montant"], op["tags"])).fetchone()
        texte = f"✓ +{dh(op['montant'])} · {source or 'revenu sans source'} · {_quand(jour, auj)}"
        return texte, _boutons([[("↩️ Annuler", f"a:r:{r['id']}")]])
    categorie = deviner_categorie(c, op["texte"])
    if not categorie:
        # Gardée en attente avec le message : le bouton choisi l'enregistrera
        c.execute("UPDATE telegram_messages SET attente=%s WHERE update_id=%s", (json.dumps(op, ensure_ascii=False), update_id))
        quoi = f" « {op['texte']} »" if op["texte"] else ""
        return f"{dh(op['montant'])}{quoi} : dans quelle catégorie ?", _clavier_categories(c, f"c:{update_id}")
    return _confirmation_depense(c, _inserer_depense(c, op, categorie, auj), auj)


def reste_a_depenser(auj: date) -> str:
    from routes.rapports import calculer_resume, resume_jour
    j = resume_jour(auj.isoformat())
    m = calculer_resume(auj.strftime("%Y-%m"), auj)
    lignes = []
    if j["budget_jour"] > 0:
        reste = j["budget_jour"] - j["depenses_variables"]
        lignes.append(f"Aujourd'hui : reste {dh(reste)} (budget {dh(j['budget_jour'])} par jour)" if reste >= 0
                      else f"Aujourd'hui : {dh(-reste)} au-delà du budget du jour ({dh(j['budget_jour'])})")
    if m["budget_total"] > 0:
        lignes.append(f"Ce mois-ci : reste {dh(m['reste_budget'])} sur {dh(m['budget_total'])}")
    lignes.append(f"Dépensé ce mois-ci : {dh(m['total_depenses'])}")
    return "\n".join(lignes)


def solde(auj: date, montant: Optional[float]) -> str:
    from routes import patrimoine
    if montant is None:
        calcule = patrimoine.liquidites_du_jour(auj)
        with db() as c:
            p = patrimoine.dernier_pointage(c, auj)
        dernier = (f"Dernier pointage : il y a {p['jours']} jour{'s' if p['jours'] > 1 else ''}" if p and p["jours"]
                   else "Dernier pointage : aujourd'hui" if p else "Jamais pointé")
        return f"Liquidités calculées : {dh(calcule)}\n{dernier}\nPour pointer, écris « solde » suivi de ton solde réel (banque + espèces)."
    r = patrimoine.pointer(auj, [{"nom": "Telegram", "montant": montant}], "Pointé par Telegram")
    if abs(r["ecart"]) < 1:
        return f"✓ Pointage noté : {dh(montant)}, comme calculé. Tout est saisi 👌"
    sens = "manque" if r["ecart"] < 0 else "est en trop"
    return (f"✓ Pointage noté : {dh(montant)} pour {dh(r['solde_calcule'])} calculés.\n"
            f"{dh(abs(r['ecart']))} {sens} : une opération oubliée ? L'écart peut s'enregistrer dans Suivi → Patrimoine.")


# ---------------------------------------------------------------- boutons
def bouton(c, data: str, auj: date) -> tuple:
    """Clic sur un bouton : (texte qui remplace le message, boutons ou None, notification courte)."""
    morceaux = data.split(":")
    if morceaux[0] == "x":
        return "Abandonné.", None, "Abandonné"
    if morceaux[0] == "a" and len(morceaux) == 3:
        table = "depenses" if morceaux[1] == "d" else "revenus"
        row = c.execute(f"DELETE FROM {table} WHERE id=%s RETURNING montant, COALESCE(description,'') description",
                        (int(morceaux[2]),)).fetchone()
        if not row:
            return "Déjà supprimée.", None, "Déjà supprimée"
        return f"↩️ Annulé : {dh(row['montant'])} {row['description']}".strip(), None, "Annulé"
    if morceaux[0] == "k" and len(morceaux) == 2:
        d = c.execute("SELECT categorie, montant FROM depenses WHERE id=%s", (int(morceaux[1]),)).fetchone()
        if not d:
            return "Cette dépense n'existe plus.", None, "Introuvable"
        return f"{dh(d['montant'])} : quelle catégorie ?", _clavier_categories(c, f"m:{morceaux[1]}", d["categorie"]), ""
    cat = c.execute("SELECT nom FROM categories WHERE id=%s AND actif=1", (int(morceaux[-1]),)).fetchone() if morceaux[-1].isdigit() else None
    if morceaux[0] == "m" and len(morceaux) == 3 and cat:
        d = c.execute("""UPDATE depenses SET categorie=%s WHERE id=%s
                         RETURNING id, date, categorie, description, montant, tags""", (cat["nom"], int(morceaux[1]))).fetchone()
        if not d:
            return "Cette dépense n'existe plus.", None, "Introuvable"
        texte, boutons = _confirmation_depense(c, d, auj)
        return texte, boutons, cat["nom"]
    if morceaux[0] == "c" and len(morceaux) == 3 and cat:
        # RETURNING donne la valeur APRÈS la mise à jour (NULL) : l'ancienne est lue dans la sous-requête,
        # verrouillée pour qu'un double clic ne l'enregistre pas deux fois
        attente = c.execute("""UPDATE telegram_messages t SET attente = NULL
                               FROM (SELECT update_id, attente FROM telegram_messages
                                     WHERE update_id = %s AND attente IS NOT NULL FOR UPDATE) avant
                               WHERE t.update_id = avant.update_id
                               RETURNING avant.attente""", (int(morceaux[1]),)).fetchone()
        if not attente:
            return "Déjà enregistrée.", None, "Déjà enregistrée"
        op = attente["attente"] if isinstance(attente["attente"], dict) else json.loads(attente["attente"])
        texte, boutons = _confirmation_depense(c, _inserer_depense(c, op, cat["nom"], auj), auj)
        return texte, boutons, cat["nom"]
    return "Ce bouton n'est plus valable.", None, ""


# ---------------------------------------------------------------- webhook
def _envoyer(texte: str, boutons: Optional[dict] = None):
    appel_telegram("sendMessage", {"chat_id": TELEGRAM_CHAT_ID, "text": texte, **({"reply_markup": boutons} if boutons else {})})


def _nouveau(c, update_id: int) -> bool:
    """True la première fois qu'un message arrive (Telegram peut l'envoyer plusieurs fois)."""
    c.execute("DELETE FROM telegram_messages WHERE le < now() - make_interval(days => %s)", (GARDE_JOURS,))
    return c.execute("INSERT INTO telegram_messages(update_id) VALUES(%s) ON CONFLICT DO NOTHING",
                     (update_id,)).rowcount == 1


def traiter(update: dict, auj: date):
    """Traite une mise à jour Telegram (message ou clic sur un bouton) et répond."""
    update_id = update.get("update_id")
    message, clic = update.get("message"), update.get("callback_query")
    chat = ((clic or {}).get("message") or message or {}).get("chat", {}).get("id")
    if update_id is None or str(chat) != TELEGRAM_CHAT_ID:
        return   # une autre conversation : ignorée sans réponse
    with db() as c:
        if not _nouveau(c, update_id):
            return
        if clic:
            texte, boutons, note = bouton(c, clic.get("data", ""), auj)
            c.commit()
            appel_telegram("answerCallbackQuery", {"callback_query_id": clic["id"], "text": note[:200]})
            try:
                appel_telegram("editMessageText", {"chat_id": TELEGRAM_CHAT_ID, "message_id": clic["message"]["message_id"],
                                                   "text": texte, **({"reply_markup": boutons} if boutons else {})})
            except RuntimeError as e:
                if "not modified" not in str(e):   # même catégorie choisie à nouveau : rien à changer
                    raise
            return
        lu = analyser((message or {}).get("text") or "")
        if lu["commande"] == "operation":
            texte, boutons = operation(c, update_id, lu, auj)
            c.commit()
            return _envoyer(texte, boutons)
    if lu["commande"] == "aide":
        _envoyer(AIDE)
    elif lu["commande"] == "reste":
        _envoyer(reste_a_depenser(auj))
    elif lu["commande"] == "solde":
        _envoyer(solde(auj, lu.get("montant")))
    else:
        _envoyer("Je n'ai pas trouvé de montant 🤔 Écris par exemple « 45 café » ou « aide ».")


@webhook.post("/webhook")
def recevoir(update: dict = Body(...), x_telegram_bot_api_secret_token: Optional[str] = Header(default=None)):
    if not configure():
        raise HTTPException(503, "Telegram non configuré")
    if not secrets.compare_digest((x_telegram_bot_api_secret_token or "").encode(), TELEGRAM_WEBHOOK_SECRET.encode()):
        raise HTTPException(401, "Non autorisé")
    try:
        traiter(update, aujourdhui())
    except Exception as e:
        # Toujours 200 : une erreur renvoyée ferait réessayer Telegram avec le même message
        print(f"[telegram] message non traité — {e!r}", flush=True)
        try:
            _envoyer(f"⚠️ Je n'ai pas pu enregistrer ça : {e}"[:300])
        except Exception:
            pass
    return {"ok": True}


# ---------------------------------------------------------------- activation (Paramètres)
def _adresse(request: Request) -> str:
    """Adresse publique du webhook : celle par laquelle l'application est ouverte (en https)."""
    hote = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"https://{hote}{CHEMIN_WEBHOOK}"


@router.get("/etat")
def etat_telegram(request: Request):
    """Saisie par Telegram : configurée (jeton et chat_id), et active (webhook déclaré à cette adresse)."""
    if not configure():
        return {"configure": False, "actif": False, "adresse": None, "erreur": None}
    try:
        info = appel_telegram("getWebhookInfo", {}) or {}
    except RuntimeError as e:
        return {"configure": True, "actif": False, "adresse": None, "erreur": str(e)}
    return {"configure": True, "actif": bool(info.get("url")) and info.get("url") == _adresse(request),
            "adresse": info.get("url") or None, "erreur": info.get("last_error_message")}


@router.post("/activer")
def activer_telegram(request: Request):
    if not configure():
        raise HTTPException(400, "Renseigne d'abord TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID sur le serveur")
    adresse = _adresse(request)
    if any(h in adresse for h in ("localhost", "127.0.0.1", "0.0.0.0")):
        raise HTTPException(400, "Telegram doit pouvoir joindre l'application : active la saisie depuis l'adresse en ligne (Vercel)")
    try:
        appel_telegram("setWebhook", {"url": adresse, "secret_token": TELEGRAM_WEBHOOK_SECRET,
                                      "allowed_updates": ["message", "callback_query"], "drop_pending_updates": True})
        appel_telegram("setMyCommands", {"commands": [
            {"command": "aide", "description": "Comment saisir une dépense"},
            {"command": "reste", "description": "Ce qu'il reste à dépenser"},
            {"command": "solde", "description": "Liquidités, et pointage du solde"}]})
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    return {"actif": True, "adresse": adresse}


@router.post("/desactiver")
def desactiver_telegram():
    if not configure():
        raise HTTPException(400, "Telegram n'est pas configuré")
    try:
        appel_telegram("deleteWebhook", {})
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    return {"actif": False}
