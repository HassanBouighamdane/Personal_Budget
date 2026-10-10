# -*- coding: utf-8 -*-
"""Mise en forme du résumé hebdomadaire, à partir des données réunies par routes/rappels.py :
texte brut (repli), message Telegram (HTML restreint de Telegram) et e-mail HTML.

L'e-mail n'utilise que des styles en ligne et des blocs simples : c'est ce que les messageries
(Gmail en tête) affichent sans surprise. Tout texte saisi par l'utilisateur est échappé."""
from datetime import date
from html import escape, unescape

MOIS_COURTS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
JOURS_COURTS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
JOURS_LONGS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

# Couleurs de l'application (cf. frontend-react/src/global.css)
MARQUE, DEP, REV, EP, ALERTE = "#6366f1", "#f43f5e", "#3b82f6", "#10b981", "#f59e0b"
TEXTE, DISCRET, BORD, FOND, PISTE = "#111827", "#6b7280", "#e5e7eb", "#f3f4f6", "#eef0f4"


def dh(v) -> str:
    return f"{round(float(v)):,}".replace(",", " ").replace("-", "−") + " DH"


def jour(d: date) -> str:
    return f"{d.day} {MOIS_COURTS[d.month - 1]}"


def delai(jours: int) -> str:
    if jours < 0:
        return f"en retard de {-jours} jour{'s' if jours < -1 else ''}"
    return {0: "aujourd'hui", 1: "demain"}.get(jours, f"dans {jours} jours")


def _signe(v) -> str:
    return ("+" if v >= 0 else "−") + dh(abs(v))


def _pct(v: float) -> str:
    return f"{abs(v) * 100:.1f} %".replace(".", ",")


def verdict(b: dict | None) -> str:
    """La phrase qui résume la semaine, en tête du message."""
    if not b:
        return ""
    if not b["dep"] and not b["rev"]:
        return "Aucune opération saisie cette semaine."
    if b["budget_hebdo"]:
        if b["reste"] >= 0:
            return f"Semaine sous le budget : {dh(b['reste'])} de marge."
        return f"Budget de la semaine dépassé de {dh(-b['reste'])}."
    return f"{dh(b['dep'])} dépensés cette semaine."


def _variation(b: dict) -> str:
    """« ▼ 12 % » par rapport à la semaine d'avant, ou chaîne vide s'il n'y a rien à comparer."""
    v = b["variation_pct"]
    if v is None:
        return ""
    return "＝ comme la semaine d'avant" if v == 0 else f"{'▲' if v > 0 else '▼'} {abs(v)} % sur la semaine d'avant"


def _faits(b: dict) -> list:
    """Faits marquants de la semaine : (emoji, texte)."""
    faits = []
    g = b["plus_grosse"]
    if g:
        quoi = g["description"] or g["categorie"]
        faits.append(("🔝", f"Plus grosse dépense : {quoi}, {dh(g['montant'])} ({JOURS_LONGS[g['date'].weekday()]})"))
    if b["jour_max"] and len([j for j in b["jours"] if j["dep"] > 0]) > 1:
        faits.append(("📍", f"Jour le plus dépensier : {JOURS_LONGS[b['jour_max']['date'].weekday()]}, {dh(b['jour_max']['dep'])}"))
    if b["dep"] and b["jours_sans"]:
        faits.append(("🌿", f"{b['jours_sans']} jour{'s' if b['jours_sans'] > 1 else ''} sans dépense"))
    return faits


def _mois(m: dict) -> str:
    ligne = f"{m['nom'].capitalize()} : {dh(m['dep'])} dépensés"
    if m["budget"]:
        ligne += f" sur {dh(m['budget'])} de budget"
    if m["projection"]:
        ligne += f", projection {dh(m['projection'])}"
    return ligne


def _livres(n: int) -> str:
    return f"{n} livre{'s' if n > 1 else ''}"


# ---------------------------------------------------------------- texte brut
def rendre_texte(d: dict) -> str:
    sections = []
    b = d["budget"]
    if b:
        lignes = ["💸 Budget", f"Dépenses : {dh(b['dep'])}" + (f" ({_variation(b)})" if _variation(b) else "")]
        if b["rev"]:
            lignes += [f"Revenus : {dh(b['rev'])}", f"Épargne : {_signe(b['epargne'])}"]
        if b["budget_hebdo"]:
            etat = f"reste {dh(b['reste'])}" if b["reste"] >= 0 else f"dépassé de {dh(-b['reste'])}"
            lignes.append(f"Budget variable : {dh(b['dep_var'])} sur {dh(b['budget_hebdo'])} ({etat})")
        if b["dep"]:
            lignes.append(" · ".join(f"{JOURS_COURTS[i]} {round(j['dep'])}" for i, j in enumerate(b["jours"])))
            lignes.append("Top : " + " · ".join(f"{c['cat']} {dh(c['montant'])}" for c in b["categories"][:3]))
        lignes += [f"{e} {t}" for e, t in _faits(b)]
        if b["mois"]:
            lignes.append(_mois(b["mois"]))
        sections.append(lignes)
    p = d["bourse"]
    if p:
        lignes = ["📈 Bourse", f"Portefeuille : {dh(p['patrimoine'])} (titres {dh(p['titres'])}, espèces {dh(p['especes'])})"]
        if p["ecart"] is not None:
            lignes.append(f"Depuis le dernier résumé : {_signe(p['ecart'])} (apports et retraits compris)")
        lignes.append(f"Performance globale : {_signe(p['perf'])}"
                      + (f" ({'+' if p['perf'] >= 0 else '−'}{_pct(p['perf_pct'])})" if p["perf_pct"] is not None else ""))
        sections.append(lignes)
    l = d["lectures"]
    if l:
        lignes = ["📚 Lectures"]
        if l["finis"]:
            pages = sum(x["pages"] or 0 for x in l["finis"])
            lignes.append("Terminé cette semaine : " + ", ".join(x["titre"] for x in l["finis"]) + (f" ({pages} pages)" if pages else ""))
        if l["en_cours"]:
            lignes.append("En cours : " + ", ".join(l["en_cours"]))
        lignes.append(f"{l['annee']} : {_livres(l['nb'])}" + (f" sur {l['objectif']}" if l["objectif"] else ""))
        sections.append(lignes)
    t = d["dettes"]
    if t:
        sections.append(["🤝 Dettes et prêts", f"On te doit : {dh(t['on_me_doit'])} · Tu dois : {dh(t['je_dois'])}"]
                        + [f"• {x['libelle']} : échéance dépassée ({jour(x['echeance'])})" for x in t["en_retard"]])
    if d["echeances"]:
        sections.append(["⏰ Échéances"] + [f"• {e['titre']} : {delai(e['jours'])} ({jour(e['date'])})" for e in d["echeances"]])
    tete = [verdict(b)] if verdict(b) else []
    return "\n\n".join(["\n".join(s) for s in [tete] + sections if s])


# ---------------------------------------------------------------- Telegram
# Telegram n'accepte que quelques balises (b, i, code, pre, blockquote). Les chiffres sont alignés
# dans des blocs <pre> (police à chasse fixe), de 24 caractères au plus pour tenir sur un téléphone.
LARGEUR_TG = 24


def _tg(texte) -> str:
    """Échappement pour Telegram : seuls & < > comptent, les apostrophes restent telles quelles."""
    return escape(str(texte), quote=False)


def _table_tg(lignes: list) -> str:
    """[(libellé, valeur)] → bloc aligné : libellés à gauche (coupés au besoin), valeurs à droite."""
    rendu = []
    for libelle, valeur in lignes:
        place = LARGEUR_TG - len(valeur) - 1
        if len(libelle) > place:
            libelle = libelle[:place - 1] + "…"
        rendu.append(_tg(f"{libelle:<{place}} {valeur}"))
    return "<pre>" + "\n".join(rendu) + "</pre>"


def _jauge_tg(part: float, legende: str) -> str:
    pleines = max(0, min(10, round(part * 10)))
    return f"<code>{'█' * pleines}{'░' * (10 - pleines)}</code> {_tg(legende)}"


def _barres_tg(lignes: list) -> str:
    """[(libellé de 3 caractères, montant)] → barres horizontales proportionnelles."""
    maxi = max(m for _, m in lignes)
    rendu = []
    for libelle, montant in lignes:
        n = max(1, round(montant / maxi * 10)) if montant > 0 else 0
        valeur = f"{round(montant):,}".replace(",", " ") if montant > 0 else "·"
        rendu.append(_tg(f"{libelle:<5} {'█' * n:<10} {valeur:>7}"))
    return "<pre>" + "\n".join(rendu) + "</pre>"


def _emoji_verdict(positif: bool | None) -> str:
    return "💤" if positif is None else "✅" if positif else "⚠️"


def _tete_tg(titre: str, periode: str, phrase: str, positif: bool | None) -> str:
    tete = f"📊 <b>{_tg(titre)}</b>\n{_tg(periode)}"
    return tete + (f"\n<blockquote>{_emoji_verdict(positif)} {_tg(phrase)}</blockquote>" if phrase else "")


def _perf(p: dict) -> str:
    return _signe(p["perf"]) + (f" ({'+' if p['perf'] >= 0 else '−'}{_pct(p['perf_pct'])})" if p["perf_pct"] is not None else "")


def _tg_lectures(l: dict, titre_finis: str) -> str:
    lignes = ["📚 <b>Lectures</b>"]
    lignes += [f"✅ {_tg(x['titre'])}" + (f" · {x['pages']} p." if x["pages"] else "") for x in l["finis"]]
    if not l["finis"] and titre_finis:
        lignes.append(_tg(titre_finis))
    lignes += [f"📖 En cours : {_tg(t)}" for t in l["en_cours"]]
    if l["objectif"]:
        lignes.append(_jauge_tg(l["nb"] / l["objectif"], f"{l['nb']} / {l['objectif']} en {l['annee']}"))
    else:
        lignes.append(f"{_livres(l['nb'])} en {l['annee']}")
    return "\n".join(lignes)


def _tg_carnet(d: dict) -> list:
    blocs = []
    t = d["dettes"]
    if t:
        blocs.append("\n".join(["🤝 <b>Dettes et prêts</b>", _table_tg([("On te doit", dh(t["on_me_doit"])), ("Tu dois", dh(t["je_dois"]))])]
                               + [f"🔴 {_tg(x['libelle'])} : échéance dépassée ({jour(x['echeance'])})" for x in t["en_retard"]]))
    if d["echeances"]:
        blocs.append("\n".join(["⏰ <b>Échéances</b>"] + [
            f"{'🔴' if x['jours'] < 0 else '🟠'} {_tg(x['titre'])}\n      <i>{delai(x['jours'])} · {jour(x['date'])}</i>" for x in d["echeances"]]))
    return blocs


def _positif_semaine(b: dict | None) -> bool | None:
    if not b or (not b["dep"] and not b["rev"]):
        return None
    return b["reste"] >= 0 if b["budget_hebdo"] else True


def rendre_telegram(d: dict) -> str:
    """Résumé de la semaine au format HTML de Telegram."""
    b = d["budget"]
    blocs = [_tete_tg("Ta semaine", f"{jour(d['lundi'])} → {jour(d['dimanche'])}", verdict(b), _positif_semaine(b))]
    if b and (b["dep"] or b["rev"]):
        chiffres = [("Dépensé", dh(b["dep"]))]
        if b["rev"]:
            chiffres += [("Reçu", dh(b["rev"])), ("Épargne", _signe(b["epargne"]))]
        if b["variation_pct"] is not None:
            chiffres.append(("Sem. d'avant", dh(b["dep_prec"])))
        lignes = ["💸 <b>Budget</b>", _table_tg(chiffres)]
        if _variation(b):
            lignes.append(_tg(_variation(b)))
        if b["budget_hebdo"]:
            part = b["dep_var"] / b["budget_hebdo"]
            lignes.append(_jauge_tg(part, f"{round(part * 100)} % du budget variable"))
        blocs.append("\n".join(lignes))
        if b["dep"]:
            blocs.append("\n".join(["🗓 <b>Jour par jour</b>", _barres_tg([(JOURS_COURTS[i], j["dep"]) for i, j in enumerate(b["jours"])])]
                                   + [f"{emoji} {_tg(texte)}" for emoji, texte in _faits(b)]))
            blocs.append("🏷 <b>Où est parti l'argent</b>\n" + _table_tg([(c["cat"], dh(c["montant"])) for c in b["categories"][:5]]))
    if b and b["mois"]:
        m = b["mois"]
        chiffres = [("Dépensé", dh(m["dep"]))] + ([("Budget", dh(m["budget"]))] if m["budget"] else []) \
            + ([("Projection", dh(m["projection"]))] if m["projection"] else [])
        blocs.append(f"📅 <b>{_tg(m['nom'].capitalize())} en cours</b>\n" + _table_tg(chiffres))
    p = d["bourse"]
    if p:
        lignes = ["📈 <b>Bourse</b>", _table_tg([("Portefeuille", dh(p["patrimoine"])), ("Titres", dh(p["titres"])), ("Espèces", dh(p["especes"]))])]
        if p["ecart"] is not None:
            lignes.append(f"{'🟢' if p['ecart'] >= 0 else '🔴'} {_signe(p['ecart'])} depuis le dernier résumé")
        lignes.append(f"Performance globale : <b>{_perf(p)}</b>")
        blocs.append("\n".join(lignes))
    if d["lectures"]:
        blocs.append(_tg_lectures(d["lectures"], ""))
    return "\n\n".join(blocs + _tg_carnet(d))


# ---------------------------------------------------------------- e-mail HTML
def _barre(part: float, couleur: str, hauteur: int = 8) -> str:
    largeur = max(0, min(100, round(part * 100)))
    return (f'<div style="background:{PISTE};border-radius:99px;height:{hauteur}px;overflow:hidden;font-size:0;line-height:0">'
            f'<div style="width:{largeur}%;background:{couleur};height:{hauteur}px;border-radius:99px"></div></div>')


def _pastille(texte: str, couleur: str) -> str:
    # Fond : la couleur à 12 % (en rgba, mieux pris en charge par les messageries que #rrggbbaa)
    r, v, bl = (int(couleur[i:i + 2], 16) for i in (1, 3, 5))
    return (f'<span style="display:inline-block;background:rgba({r},{v},{bl},.12);color:{couleur};font-size:12px;font-weight:700;'
            f'padding:2px 8px;border-radius:99px;white-space:nowrap">{texte}</span>')


def _carte(titre: str, contenu: str) -> str:
    return (f'<div style="background:#ffffff;border:1px solid {BORD};border-radius:14px;padding:18px 20px;margin:0 0 12px">'
            f'<div style="font-size:12px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;color:{DISCRET};margin:0 0 12px">{titre}</div>'
            f'{contenu}</div>')


def _chiffres(cases: list) -> str:
    """Rangée de chiffres clés : [(libellé, valeur, couleur, complément HTML)]."""
    largeur = 100 // len(cases)
    tds = "".join(
        f'<td width="{largeur}%" valign="top" style="padding:0 6px 0 0">'
        f'<div style="font-size:12px;color:{DISCRET}">{lib}</div>'
        f'<div style="font-size:20px;font-weight:700;color:{couleur};white-space:nowrap;margin-top:2px">{valeur}</div>'
        f'{f"<div style=margin-top:4px>{plus}</div>" if plus else ""}</td>'
        for lib, valeur, couleur, plus in cases)
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse"><tr>{tds}</tr></table>'


def _ligne(gauche: str, droite: str = "", style: str = "") -> str:
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;{style}"><tr>'
            f'<td style="font-size:14px;color:{TEXTE}">{gauche}</td>'
            f'<td align="right" style="font-size:14px;font-weight:600;color:{TEXTE};white-space:nowrap;padding-left:8px">{droite}</td></tr></table>')


def _discret(texte: str, marge: str = "8px 0 0") -> str:
    return f'<div style="font-size:13px;color:{DISCRET};margin:{marge}">{texte}</div>'


def _carte_budget(b: dict) -> str:
    e = escape
    v = b["variation_pct"]
    badge = "" if v is None else _pastille("＝ stable" if v == 0 else f"{'▲' if v > 0 else '▼'} {abs(v)} %", DISCRET if v == 0 else DEP if v > 0 else EP)
    cases = [("Dépensé", dh(b["dep"]), DEP, badge)]
    if b["rev"]:
        cases += [("Reçu", dh(b["rev"]), REV, ""), ("Épargne", _signe(b["epargne"]), EP if b["epargne"] >= 0 else DEP, "")]
    html = _chiffres(cases)
    if v is not None:
        html += _discret(f"Semaine d'avant : {dh(b['dep_prec'])}", "6px 0 0")
    if b["budget_hebdo"]:
        part = b["dep_var"] / b["budget_hebdo"]
        couleur = DEP if part > 1 else ALERTE if part > 0.85 else EP
        etat = f"reste {dh(b['reste'])}" if b["reste"] >= 0 else f"dépassé de {dh(-b['reste'])}"
        html += (f'<div style="margin:16px 0 6px">{_ligne("Budget variable de la semaine", f"{round(part * 100)} %")}</div>'
                 + _barre(part, couleur, 10) + _discret(f"{dh(b['dep_var'])} sur {dh(b['budget_hebdo'])} · {etat}", "6px 0 0"))
    return _carte("💸 Budget", html)


def _carte_jours(b: dict) -> str:
    maxi = max(j["dep"] for j in b["jours"])
    lignes = ""
    for i, j in enumerate(b["jours"]):
        est_max = j["dep"] == maxi
        barre = _barre(j["dep"] / maxi, DEP if est_max else MARQUE, 12) if j["dep"] > 0 else ""
        montant = dh(j["dep"]) if j["dep"] > 0 else "—"
        lignes += (f'<tr><td width="40" style="font-size:13px;color:{DISCRET};padding:5px 0">{JOURS_COURTS[i]}</td>'
                   f'<td style="padding:5px 10px 5px 0">{barre}</td>'
                   f'<td width="84" align="right" style="font-size:13px;font-weight:{700 if est_max else 500};'
                   f'color:{TEXTE if j["dep"] > 0 else DISCRET};white-space:nowrap">{montant}</td></tr>')
    html = f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">{lignes}</table>'
    faits = _faits(b)
    if faits:
        html += f'<div style="border-top:1px solid {BORD};margin:12px 0 0;padding:10px 0 0">' + "".join(
            f'<div style="font-size:13px;color:{TEXTE};margin:4px 0">{emoji}&nbsp; {escape(texte)}</div>' for emoji, texte in faits) + "</div>"
    return _carte("🗓️ Jour par jour", html)


def _carte_categories(b: dict) -> str:
    html = ""
    for c in b["categories"][:5]:
        part = c["montant"] / b["dep"]
        html += (f'<div style="margin:0 0 10px">{_ligne(escape(c["cat"]), dh(c["montant"]))}'
                 f'<div style="margin-top:5px">{_barre(part, MARQUE, 6)}</div></div>')
    reste = len(b["categories"]) - 5
    if reste > 0:
        html += _discret(f"et {reste} autre{'s' if reste > 1 else ''} catégorie{'s' if reste > 1 else ''}", "0")
    return _carte("🏷️ Où est parti l'argent", html)


def _carte_mois(m: dict) -> str:
    html = _ligne(f"Dépensé en {escape(m['nom'])}", dh(m["dep"]))
    if m["budget"]:
        part = m["dep"] / m["budget"]
        html += f'<div style="margin:8px 0 0">{_barre(part, DEP if part > 1 else MARQUE, 10)}</div>'
        html += _discret(f"{round(part * 100)} % du budget du mois ({dh(m['budget'])})", "6px 0 0")
    if m["projection"]:
        depasse = m["budget"] and m["projection"] > m["budget"]
        html += _discret(f"À ce rythme, fin de mois à <b style=\"color:{DEP if depasse else TEXTE}\">{dh(m['projection'])}</b>")
    return _carte(f"📅 {escape(m['nom'].capitalize())}", html)


def _carte_bourse(p: dict) -> str:
    badge = "" if p["ecart"] is None else _pastille(_signe(p["ecart"]), EP if p["ecart"] >= 0 else DEP)
    html = _chiffres([("Portefeuille", dh(p["patrimoine"]), TEXTE, badge)])
    if p["ecart"] is not None:
        html += _discret("Écart depuis le dernier résumé, apports et retraits compris", "6px 0 0")
    html += f'<div style="border-top:1px solid {BORD};margin:12px 0 0;padding:10px 0 0">'
    html += _ligne("Titres", dh(p["titres"]), "margin:0 0 4px") + _ligne("Espèces", dh(p["especes"]), "margin:0 0 4px")
    perf = _signe(p["perf"]) + (f" ({'+' if p['perf'] >= 0 else '−'}{_pct(p['perf_pct'])})" if p["perf_pct"] is not None else "")
    html += _ligne("Performance globale", f'<span style="color:{EP if p["perf"] >= 0 else DEP}">{perf}</span>') + "</div>"
    return _carte("📈 Bourse", html)


def _carte_lectures(l: dict) -> str:
    e = escape
    html = "".join(f'<div style="font-size:14px;color:{TEXTE};margin:0 0 6px">✅&nbsp; <b>{e(x["titre"])}</b>'
                   + (f' <span style="color:{DISCRET}">· {x["pages"]} pages</span>' if x["pages"] else "") + "</div>" for x in l["finis"])
    html += "".join(f'<div style="font-size:14px;color:{TEXTE};margin:0 0 6px">📖&nbsp; En cours : {e(t)}</div>' for t in l["en_cours"])
    if not l["finis"]:
        html += _discret(f"Aucun livre terminé {l.get('periode', 'cette semaine')}.", "0 0 6px")
    if l["objectif"]:
        html += (f'<div style="margin:10px 0 6px">{_ligne(f"Objectif {l["annee"]}", f"{l["nb"]} / {l["objectif"]}")}</div>'
                 + _barre(l["nb"] / l["objectif"], EP, 8))
    else:
        html += _discret(f"{_livres(l['nb'])} en {l['annee']}")
    return _carte("📚 Lectures", html)


def _carte_carnet(t: dict | None, echeances: list) -> str:
    e = escape
    html = ""
    if t:
        html += _chiffres([("On te doit", dh(t["on_me_doit"]), EP, ""), ("Tu dois", dh(t["je_dois"]), DEP if t["je_dois"] else TEXTE, "")])
        html += "".join(f'<div style="font-size:13px;color:{TEXTE};margin:10px 0 0">{_pastille("échéance dépassée", DEP)}&nbsp; '
                        f'{e(x["libelle"])} <span style="color:{DISCRET}">· {jour(x["echeance"])}</span></div>' for x in t["en_retard"])
    if echeances:
        if t:
            html += f'<div style="border-top:1px solid {BORD};margin:14px 0 0;padding:4px 0 0"></div>'
        html += "".join(f'<div style="font-size:14px;color:{TEXTE};margin:8px 0 0">{_pastille(delai(x["jours"]), DEP if x["jours"] < 0 else ALERTE)}&nbsp; '
                        f'{e(x["titre"])} <span style="color:{DISCRET}">· {jour(x["date"])}</span></div>' for x in echeances)
    return _carte("🤝 Dettes · ⏰ Échéances" if t and echeances else "🤝 Dettes et prêts" if t else "⏰ Échéances", html)


def _page(surtitre: str, titre: str, phrase: str, cartes: list, pied: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titre)}</title></head>
<body style="margin:0;padding:0;background:{FOND};font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:{TEXTE}">
<div style="max-width:560px;margin:0 auto;padding:16px 12px 24px">
<div style="background:{MARQUE};background-image:linear-gradient(135deg,{MARQUE},#4338ca);border-radius:14px;padding:22px 20px;margin:0 0 12px">
<div style="font-size:12px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;color:#c7d2fe">{escape(surtitre)}</div>
<div style="font-size:24px;font-weight:700;color:#ffffff;margin:6px 0 0">{escape(titre)}</div>
{f'<div style="font-size:15px;color:#e0e7ff;margin:8px 0 0">{escape(phrase)}</div>' if phrase else ''}
</div>
{''.join(cartes)}
<div style="font-size:12px;color:{DISCRET};text-align:center;margin:16px 0 0">{escape(pied)}</div>
</div></body></html>"""


def rendre_email(d: dict) -> str:
    b = d["budget"]
    cartes = []
    if b:
        cartes.append(_carte_budget(b))
        if b["dep"]:
            cartes += [_carte_jours(b), _carte_categories(b)]
        if b["mois"]:
            cartes.append(_carte_mois(b["mois"]))
    if d["bourse"]:
        cartes.append(_carte_bourse(d["bourse"]))
    if d["lectures"]:
        cartes.append(_carte_lectures(d["lectures"]))
    if d["dettes"] or d["echeances"]:
        cartes.append(_carte_carnet(d["dettes"], d["echeances"]))
    return _page("Mon Budget · résumé de la semaine", f"{jour(d['lundi'])} → {jour(d['dimanche'])}", verdict(b), cartes,
                 "Envoyé chaque lundi par ton application Mon Budget")


# ================================================================ résumé du mois
MOIS_LONGS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
              "novembre", "décembre"]


def _nom_mois(mois: str, annee: bool = True) -> str:
    """« 2026-09 » → « septembre 2026 »."""
    return MOIS_LONGS[int(mois[5:]) - 1] + (f" {mois[:4]}" if annee else "")


def verdict_mois(b: dict | None) -> str:
    if not b:
        return ""
    if not b["dep"] and not b["rev"]:
        return "Aucune opération saisie ce mois-ci."
    ep, obj = b["epargne"], b["objectif"]
    if ep < 0:
        return f"Mois dans le rouge : {dh(-ep)} dépensés de plus que reçus."
    if obj and ep >= obj:
        return f"Objectif d'épargne atteint : {dh(ep)} mis de côté."
    if obj:
        return f"{dh(ep)} mis de côté, il manquait {dh(obj - ep)} pour l'objectif."
    return f"{dh(ep)} mis de côté ce mois-ci."


def _positif_mois(b: dict | None) -> bool | None:
    if not b or (not b["dep"] and not b["rev"]):
        return None
    return b["epargne"] >= (b["objectif"] or 0)


def _variation_mois(b: dict) -> str:
    v = b["variation_pct"]
    if v is None:
        return ""
    return "＝ comme le mois d'avant" if v == 0 else f"{'▲' if v > 0 else '▼'} {abs(v)} % sur le mois d'avant"


def _depassements(b: dict) -> str:
    n = b["nb_depassees"]
    return f"{n} catégorie{'s' if n > 1 else ''} au-dessus de {'leur' if n > 1 else 'son'} budget" if n else "Aucune catégorie au-dessus de son budget"


def _depense(t: dict) -> str:
    """Libellé d'une grosse dépense : sa description, à défaut sa catégorie."""
    return t["description"] or t["categorie"]


def _bourse_mois(p: dict) -> list:
    """Lignes (libellé, valeur) de l'activité Bourse du mois ; les mouvements nuls sont omis."""
    lignes = [("Résultat du mois", _signe(p["resultat"]))] if p["resultat"] else []
    lignes += [(lib, dh(v)) for lib, v in (("Dividendes", p["dividendes"]), ("Apports", p["apports"]), ("Retraits", p["retraits"])) if v]
    return lignes


def rendre_texte_mois(d: dict) -> str:
    sections = []
    b = d["budget"]
    if b:
        lignes = ["💸 Budget", f"Dépenses : {dh(b['dep'])}" + (f" ({_variation_mois(b)})" if _variation_mois(b) else "")]
        if b["rev"]:
            lignes += [f"Revenus : {dh(b['rev'])}", f"Épargne : {_signe(b['epargne'])} ({b['taux']:g} % des revenus)".replace(".", ",")]
        if b["budget"]:
            lignes.append(f"Budget : {round(b['dep'] / b['budget'] * 100)} % utilisé ({dh(b['dep'])} sur {dh(b['budget'])})")
        if b["dep"]:
            lignes.append(_depassements(b))
            lignes += [f"• {c['cat']} : {dh(c['reel'])}" + (f" sur {dh(c['budget'])}" if c["budget"] else "") for c in b["categories"][:6]]
            lignes.append("Plus grosses dépenses : " + " · ".join(f"{_depense(t)} {dh(t['montant'])}" for t in b["top"][:3]))
        sections.append(lignes)
    p = d["bourse"]
    if p:
        sections.append(["📈 Bourse", f"Portefeuille : {dh(p['patrimoine'])}"] + [f"{lib} : {val}" for lib, val in _bourse_mois(p)]
                        + [f"Performance globale : {_perf(p)}"])
    l = d["lectures"]
    if l:
        lignes = ["📚 Lectures", f"Terminés ce mois-ci : {', '.join(x['titre'] for x in l['finis'])}" if l["finis"] else "Aucun livre terminé ce mois-ci"]
        if l["en_cours"]:
            lignes.append("En cours : " + ", ".join(l["en_cours"]))
        lignes.append(f"{l['annee']} : {_livres(l['nb'])}" + (f" sur {l['objectif']}" if l["objectif"] else ""))
        sections.append(lignes)
    t = d["dettes"]
    if t:
        sections.append(["🤝 Dettes et prêts", f"On te doit : {dh(t['on_me_doit'])} · Tu dois : {dh(t['je_dois'])}"]
                        + [f"• {x['libelle']} : échéance dépassée ({jour(x['echeance'])})" for x in t["en_retard"]])
    if d["echeances"]:
        sections.append(["⏰ Échéances du mois qui commence"] + [f"• {e['titre']} : {delai(e['jours'])} ({jour(e['date'])})" for e in d["echeances"]])
    tete = [verdict_mois(b)] if verdict_mois(b) else []
    return "\n\n".join(["\n".join(s) for s in [tete] + sections if s])


def rendre_telegram_mois(d: dict) -> str:
    b = d["budget"]
    blocs = [_tete_tg(f"Ton mois de {_nom_mois(d['mois'], False)}", f"Bilan de {_nom_mois(d['mois'])}", verdict_mois(b), _positif_mois(b))]
    if b and (b["dep"] or b["rev"]):
        chiffres = [("Dépensé", dh(b["dep"]))]
        if b["rev"]:
            chiffres += [("Reçu", dh(b["rev"])), ("Épargne", _signe(b["epargne"]))]
        if b["variation_pct"] is not None:
            chiffres.append(("Mois d'avant", dh(b["dep_prec"])))
        lignes = ["💸 <b>Budget</b>", _table_tg(chiffres)]
        if _variation_mois(b):
            lignes.append(_tg(_variation_mois(b)))
        if b["budget"]:
            part = b["dep"] / b["budget"]
            lignes.append(_jauge_tg(part, f"{round(part * 100)} % du budget du mois"))
        if b["rev"] and b["objectif"]:
            lignes.append(_jauge_tg(b["epargne"] / b["objectif"], f"{max(0, round(b['epargne'] / b['objectif'] * 100))} % de l'objectif d'épargne"))
        blocs.append("\n".join(lignes))
        if b["dep"]:
            blocs.append("🗓 <b>Au fil du mois</b>\n" + _barres_tg([(s["libelle"], s["dep"]) for s in b["semaines"]]))
            # Les catégories dépassées sont nommées sous le tableau : un émoji dans un bloc aligné le décale
            depassees = [c["cat"] for c in b["categories"] if c["budget"] and c["reel"] > c["budget"]]
            blocs.append("\n".join(["🏷 <b>Catégories</b>", _table_tg([(c["cat"], dh(c["reel"])) for c in b["categories"][:6]]),
                                    ("⚠️ " if depassees else "✅ ") + _tg(_depassements(b)) + (" : " + _tg(", ".join(depassees)) if depassees else "")]))
            blocs.append("🔝 <b>Plus grosses dépenses</b>\n" + _table_tg([(_depense(t), dh(t["montant"])) for t in b["top"][:5]]))
    p = d["bourse"]
    if p:
        blocs.append("\n".join(["📈 <b>Bourse</b>", _table_tg([("Portefeuille", dh(p["patrimoine"]))] + _bourse_mois(p)),
                                f"Performance globale : <b>{_perf(p)}</b>"]))
    if d["lectures"]:
        blocs.append(_tg_lectures(d["lectures"], "Aucun livre terminé ce mois-ci"))
    return "\n\n".join(blocs + _tg_carnet(d))


def _carte_bilan_mois(b: dict) -> str:
    v = b["variation_pct"]
    badge = "" if v is None else _pastille("＝ stable" if v == 0 else f"{'▲' if v > 0 else '▼'} {abs(v)} %", DISCRET if v == 0 else DEP if v > 0 else EP)
    cases = [("Dépensé", dh(b["dep"]), DEP, badge)]
    if b["rev"]:
        cases += [("Reçu", dh(b["rev"]), REV, ""), ("Épargne", _signe(b["epargne"]), EP if b["epargne"] >= 0 else DEP, "")]
    html = _chiffres(cases)
    if v is not None:
        html += _discret(f"Mois d'avant : {dh(b['dep_prec'])}", "6px 0 0")
    if b["budget"]:
        part = b["dep"] / b["budget"]
        etat = f"reste {dh(b['budget'] - b['dep'])}" if part <= 1 else f"dépassé de {dh(b['dep'] - b['budget'])}"
        html += (f'<div style="margin:16px 0 6px">{_ligne("Budget du mois", f"{round(part * 100)} %")}</div>'
                 + _barre(part, DEP if part > 1 else ALERTE if part > 0.9 else EP, 10)
                 + _discret(f"{dh(b['dep'])} sur {dh(b['budget'])} · {etat}", "6px 0 0"))
    if b["rev"] and b["objectif"]:
        part = b["epargne"] / b["objectif"]
        html += (f'<div style="margin:16px 0 6px">{_ligne("Objectif d&#39;épargne", f"{max(0, round(part * 100))} %")}</div>'
                 + _barre(part, EP if part >= 1 else MARQUE, 10)
                 + _discret(f"{_signe(b['epargne'])} sur {dh(b['objectif'])} · {f'{b['taux']:g}'.replace('.', ',')} % des revenus épargnés", "6px 0 0"))
    return _carte("💸 Bilan du mois", html)


def _carte_barres(titre: str, lignes: list, largeur_libelle: int = 52) -> str:
    """Barres horizontales : [(libellé, montant, mise en avant)]."""
    maxi = max(m for _, m, _ in lignes) or 1
    rangs = ""
    for libelle, montant, fort in lignes:
        barre = _barre(montant / maxi, DEP if fort else MARQUE, 12) if montant > 0 else ""
        rangs += (f'<tr><td width="{largeur_libelle}" style="font-size:13px;color:{DISCRET};padding:5px 0;white-space:nowrap">{escape(libelle)}</td>'
                  f'<td style="padding:5px 10px 5px 6px">{barre}</td>'
                  f'<td width="84" align="right" style="font-size:13px;font-weight:{700 if fort else 500};'
                  f'color:{TEXTE if montant > 0 else DISCRET};white-space:nowrap">{dh(montant) if montant > 0 else "—"}</td></tr>')
    return _carte(titre, f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">{rangs}</table>')


def _carte_categories_mois(b: dict) -> str:
    html = ""
    for c in b["categories"][:8]:
        depasse = bool(c["budget"]) and c["reel"] > c["budget"]
        droite = dh(c["reel"]) + (f' <span style="color:{DISCRET};font-weight:400">/ {dh(c["budget"])}</span>' if c["budget"] else "")
        gauche = escape(c["cat"]) + (f'&nbsp; {_pastille("dépassé", DEP)}' if depasse else "")
        part = c["reel"] / c["budget"] if c["budget"] else c["reel"] / b["dep"]
        html += (f'<div style="margin:0 0 10px">{_ligne(gauche, droite)}'
                 f'<div style="margin-top:5px">{_barre(part, DEP if depasse else MARQUE, 6)}</div></div>')
    reste = len(b["categories"]) - 8
    html += _discret(_depassements(b) + (f" · {reste} autre{'s' if reste > 1 else ''} non affichée{'s' if reste > 1 else ''}" if reste > 0 else ""), "0")
    return _carte("🏷️ Budget par catégorie", html)


def _carte_top(b: dict) -> str:
    html = "".join(
        f'<div style="margin:0 0 8px">{_ligne(escape(_depense(t)), dh(t["montant"]))}'
        + _discret(f"{escape(t['categorie'])} · {jour(t['date'])}", "1px 0 0") + "</div>" for t in b["top"][:5])
    return _carte("🔝 Plus grosses dépenses", html)


def _carte_bourse_mois(p: dict) -> str:
    html = _chiffres([("Portefeuille", dh(p["patrimoine"]), TEXTE, "")])
    html += f'<div style="border-top:1px solid {BORD};margin:12px 0 0;padding:10px 0 0">'
    html += "".join(_ligne(lib, val, "margin:0 0 4px") for lib, val in _bourse_mois(p))
    html += _ligne("Performance globale", f'<span style="color:{EP if p["perf"] >= 0 else DEP}">{_perf(p)}</span>') + "</div>"
    return _carte("📈 Bourse", html)


def rendre_email_mois(d: dict) -> str:
    b = d["budget"]
    cartes = []
    if b:
        cartes.append(_carte_bilan_mois(b))
        if b["dep"]:
            maxi = max(s["dep"] for s in b["semaines"])
            cartes.append(_carte_barres("🗓️ Au fil du mois", [(f"Du {s['libelle']}", s["dep"], s["dep"] == maxi) for s in b["semaines"]], 72))
            cartes += [_carte_categories_mois(b), _carte_top(b)]
        if len(b["evolution"]) > 1:
            cartes.append(_carte_barres("📉 Dépenses des derniers mois", [
                (f"{MOIS_COURTS[int(e['m'][5:]) - 1]} {e['m'][2:4]}", e["dep"], e["m"] == d["mois"]) for e in b["evolution"]], 72))
    if d["bourse"]:
        cartes.append(_carte_bourse_mois(d["bourse"]))
    if d["lectures"]:
        cartes.append(_carte_lectures(d["lectures"]))
    if d["dettes"] or d["echeances"]:
        cartes.append(_carte_carnet(d["dettes"], d["echeances"]))
    return _page("Mon Budget · bilan du mois", _nom_mois(d["mois"]).capitalize(), verdict_mois(b), cartes,
                 "Envoyé le 1er de chaque mois par ton application Mon Budget")
