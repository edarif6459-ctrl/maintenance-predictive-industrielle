"""Envoi d'alertes : Email (SMTP / Gmail) et Telegram. Sans dépendance externe.

Les identifiants sont lus (par ordre de priorité) :
  1. settings.json   -> enregistré depuis l'onglet « Notifications » de l'application
  2. st.secrets      -> .streamlit/secrets.toml (ou Secrets de Streamlit Cloud)
  3. variables d'environnement / fichier .env (EMAIL_USER, EMAIL_PASSWORD, EMAIL_TO, TELEGRAM_TOKEN ...)
"""
import json
import os
import smtplib
import ssl
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")


# ───────────────────────── configuration ─────────────────────────
def _read_dotenv():
    out = {}
    try:
        with open(os.path.join(BASE_DIR, ".env"), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return out


def _env(name, dotenv):
    return os.environ.get(name) or dotenv.get(name) or ""


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(email=None, telegram=None):
    """Enregistre (ou fusionne) la config dans settings.json. Retourne (ok, message)."""
    data = load_settings()
    if email is not None:
        data["email"] = email
    if telegram is not None:
        data["telegram"] = telegram
    try:
        tmp = SETTINGS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_FILE)
        try:
            os.chmod(SETTINGS_FILE, 0o600)
        except Exception:
            pass
        return True, SETTINGS_FILE
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def get_config(secrets=None):
    """Retourne (email_cfg | None, telegram_cfg | None)."""
    secrets = secrets or {}
    saved, dotenv = load_settings(), _read_dotenv()

    em = dict(saved.get("email") or {})
    if not (em.get("user") and em.get("password") and em.get("to")):
        s = dict(secrets.get("email") or {})
        if s.get("to") and (s.get("host") or s.get("user")):
            em = s
    if not (em.get("user") and em.get("password") and em.get("to")):
        user, pwd, to = _env("EMAIL_USER", dotenv), _env("EMAIL_PASSWORD", dotenv), _env("EMAIL_TO", dotenv)
        if user and pwd:
            em = {"host": _env("EMAIL_HOST", dotenv) or "smtp.gmail.com",
                  "port": _env("EMAIL_PORT", dotenv) or 587, "user": user, "password": pwd, "to": to or user}
    em = em if (em.get("user") and em.get("password") and em.get("to")) else None
    if em:
        em.setdefault("host", "smtp.gmail.com")
        em.setdefault("port", 587)

    tg = dict(saved.get("telegram") or {})
    if not (tg.get("token") and tg.get("chat_id")):
        s = dict(secrets.get("telegram") or {})
        if s.get("token") and s.get("chat_id"):
            tg = s
    if not (tg.get("token") and tg.get("chat_id")):
        tok, cid = _env("TELEGRAM_TOKEN", dotenv), _env("TELEGRAM_CHAT_ID", dotenv)
        if tok and cid:
            tg = {"token": tok, "chat_id": cid}
    tg = tg if (tg.get("token") and tg.get("chat_id")) else None
    return em, tg


# ───────────────────────── Email ─────────────────────────
def _clean_password(pwd):
    # Google affiche le mot de passe d'application par blocs de 4 séparés par des espaces
    return "".join(str(pwd).split())


def _friendly_email_error(e, host):
    if isinstance(e, smtplib.SMTPAuthenticationError):
        if "gmail" in host.lower():
            return ("Gmail a refusé la connexion. Il faut un « mot de passe d'application » (16 lettres), "
                    "pas le mot de passe normal du compte. Active d'abord la validation en 2 étapes : "
                    "https://myaccount.google.com/apppasswords")
        return "Identifiant ou mot de passe SMTP refusé."
    if isinstance(e, (smtplib.SMTPConnectError, ConnectionError, TimeoutError, OSError)):
        return f"Impossible de joindre {host} (internet, pare-feu ou port bloqué) : {e}"
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        return "Adresse destinataire refusée par le serveur."
    return f"{type(e).__name__}: {e}"


def send_email(cfg, subject, body):
    """cfg : dict(host, port, user, password, to[, sender]). Retourne (ok, message)."""
    host = str(cfg.get("host") or "smtp.gmail.com").strip()
    try:
        port = int(cfg.get("port") or 587)
        user = str(cfg.get("user", "")).strip()
        pwd = _clean_password(cfg.get("password", ""))
        to = [x.strip() for x in str(cfg["to"]).replace(";", ",").split(",") if x.strip()]
        if not to:
            return False, "Aucun destinataire."
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = cfg.get("sender") or user
        msg["To"] = ", ".join(to)
        msg.set_content(body)
        ctx = ssl.create_default_context()
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=25, context=ctx)
        else:
            server = smtplib.SMTP(host, port, timeout=25)
            server.ehlo()
            server.starttls(context=ctx)
            server.ehlo()
        with server:
            if user:
                server.login(user, pwd)
            server.send_message(msg)
        return True, ", ".join(to)
    except Exception as e:
        return False, _friendly_email_error(e, host)


# ───────────────────────── Telegram ─────────────────────────
def _tg_call(token, method, params=None):
    url = f"https://api.telegram.org/bot{str(token).strip()}/{method}"
    data = urllib.parse.urlencode(params or {}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=25) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"ok": False, "description": f"HTTP {e.code}"}


def _friendly_tg_error(desc):
    d = (desc or "").lower()
    if "chat not found" in d:
        return ("Chat introuvable : ouvre ton bot dans Telegram et appuie sur START (ou envoie-lui un message), "
                "puis vérifie le chat_id.")
    if "unauthorized" in d or "not found" in d:
        return "Token invalide : recopie le token donné par @BotFather."
    return desc or "Erreur Telegram"


def send_telegram(cfg, text):
    """cfg : dict(token, chat_id). Retourne (ok, message)."""
    try:
        res = _tg_call(cfg["token"], "sendMessage", {"chat_id": str(cfg["chat_id"]).strip(), "text": text[:4000]})
        if res.get("ok"):
            return True, "Telegram"
        return False, _friendly_tg_error(res.get("description"))
    except Exception as e:
        return False, f"Impossible de joindre Telegram (internet ?) : {type(e).__name__}: {e}"


def find_telegram_chat_id(token):
    """Cherche le chat_id dans les derniers messages reçus par le bot. Retourne (chat_id | None, message)."""
    try:
        res = _tg_call(token, "getUpdates")
        if not res.get("ok"):
            return None, _friendly_tg_error(res.get("description"))
        for u in reversed(res.get("result", [])):
            m = u.get("message") or u.get("channel_post") or u.get("my_chat_member") or {}
            chat = m.get("chat")
            if chat and chat.get("id"):
                return str(chat["id"]), chat.get("first_name") or chat.get("title") or ""
        return None, "Aucun message trouvé : envoie d'abord /start à ton bot dans Telegram, puis réessaie."
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
