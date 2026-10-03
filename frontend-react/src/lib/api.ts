/* Appels à l'API FastAPI (même origine, cookie de session HttpOnly envoyé automatiquement) */
import { notifications } from '@mantine/notifications';

let surNonAuthentifie: () => void = () => {};

/** Action à exécuter sur toute réponse 401 (session expirée) : App ramène à l'écran de connexion */
export function definirSurNonAuthentifie(action: () => void) {
  surNonAuthentifie = action;
}

export function toast(message: string, succes = true) {
  notifications.show({ message, color: succes ? 'emeraude' : 'rouge', autoClose: 2500 });
}

export class ErreurApi extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type Options = {
  method?: string;
  body?: unknown;
  /** false sur /api/login : un 401 y veut dire « identifiants incorrects », pas « session expirée » */
  sessionRequise?: boolean;
};

/** fetch + affichage du message d'erreur du serveur (erreurs Pydantic comprises) ; 204 → undefined */
export async function api<T = unknown>(path: string, options: Options = {}): Promise<T> {
  const { method = 'GET', body, sessionRequise = true } = options;
  let reponse: Response;
  try {
    reponse = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (e) {
    toast('Connexion impossible — vérifie ta connexion internet', false);
    throw e;
  }
  if (reponse.status === 401 && sessionRequise) {
    surNonAuthentifie();
    throw new ErreurApi(401, 'Non authentifié');
  }
  if (!reponse.ok) {
    let message = 'Erreur';
    try {
      const detail = (await reponse.json()).detail;
      message = Array.isArray(detail) ? detail.map((d: { msg: string }) => d.msg).join(' · ') : detail || message;
    } catch { /* corps non JSON */ }
    toast(message, false);
    throw new ErreurApi(reponse.status, message);
  }
  if (reponse.status !== 204) return reponse.json();
  return undefined as T;
}

/** Variante qui n'affiche jamais d'erreur : renvoie null en cas d'échec */
export async function apiSilencieux<T>(path: string): Promise<T | null> {
  try {
    const reponse = await fetch(path);
    return reponse.ok ? await reponse.json() : null;
  } catch {
    return null;
  }
}
