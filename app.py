"""
Maintenance Prédictive Industrielle (dataset AI4I 2020)
Lancer en local :  streamlit run app.py
"""
import base64
import hashlib
import os
import subprocess
import sys
from functools import lru_cache
from types import SimpleNamespace

import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image

from i18n import LANGS, tr

# ───────────────────────── CONFIG ─────────────────────────
APP_NAME = "Maintenance Prédictive Industrielle"
APP_TAGLINE = "Voir la panne avant qu'elle arrive"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_CSV = os.path.join(BASE_DIR, "ai4i2020.csv")
LIVE_CSV = os.path.join(BASE_DIR, "ai4i2020_live.csv")   # données + nouvelles saisies

ASSETS = BASE_DIR

try:
    _page_icon = Image.open(os.path.join(ASSETS, "logo.png"))
except Exception:
    _page_icon = "⚙️"

st.set_page_config(page_title=APP_NAME, page_icon=_page_icon, layout="wide",
                   initial_sidebar_state="expanded")

# ── plotly : si le module manque (installation locale incomplète), on tente de l'installer ──
try:
    import plotly.express as px
except ModuleNotFoundError:
    with st.spinner("Installation de plotly (une seule fois)…"):
        subprocess.run([sys.executable, "-m", "pip", "install", "plotly"], check=False)
    try:
        import plotly.express as px
    except ModuleNotFoundError:
        st.error("Le module **plotly** est introuvable. Ferme l'app puis lance dans le terminal :")
        st.code("python -m pip install -r requirements.txt", language="bash")
        st.stop()

import extras   # noqa: E402  (après plotly)

STREAMLIT_NEW = tuple(int(x) for x in st.__version__.split(".")[:2] if x.isdigit()) >= (1, 50)

# Langue et thème (choisis dans la barre latérale / page de connexion)
LANG = st.session_state.get("lang", "fr")
DARK = bool(st.session_state.get("dark", False))


def T(key, **kw):
    return tr(key, LANG, **kw)


# Palette : graphite industriel + cuivre + vert-de-gris
INK, COPPER, TEAL = "#0E1B24", "#E8833A", "#1FB5A8"
RED, BLUE, AMBER = "#E5484D", "#3E7CB1", "#F2B134"
COLORS = {"Normal": TEAL, "Panne": RED}
MODES = {k: T("mode_" + k) for k in ("TWF", "HDF", "PWF", "OSF", "RNF")}


@lru_cache(maxsize=None)
def asset_uri(filename):
    """Fichier du dossier assets/ -> data URI (utilisable dans le HTML / CSS)."""
    mime = "image/jpeg" if filename.endswith(".jpg") else "image/png"
    try:
        with open(os.path.join(ASSETS, filename), "rb") as f:
            return f"data:{mime};base64," + base64.b64encode(f.read()).decode()
    except Exception:
        return ""


def icon_uri(name):
    return asset_uri(f"{name}.png")


LOGO_URI = icon_uri("logo")

# ───────────────────────── STYLE ─────────────────────────
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700&family=Instrument+Sans:wght@400;500;600&display=swap');

.stApp {background-color:#F2F5F6; background-image:url('__TILE__'); background-repeat:repeat;}
.stApp, .stApp p, .stApp label, .stApp li, .stApp input, .stApp button, .stApp textarea
  {font-family:'Instrument Sans', 'Segoe UI', sans-serif;}
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .hero h1, .kpi .v, .login-brand h1
  {font-family:'Bricolage Grotesque', 'Segoe UI', sans-serif; letter-spacing:-.01em;}
[data-testid="stHeader"] {background:transparent;}
.block-container {padding-top:1.4rem; padding-bottom:2rem; max-width:1400px;}
#MainMenu, footer {visibility:hidden;}

/* ── barre latérale ── */
[data-testid="stSidebar"] {background:linear-gradient(180deg, __INK__ 0%, #16303d 100%);}
[data-testid="stSidebar"] * {color:#dbe7ec;}
[data-testid="stSidebar"] button *, [data-testid="stSidebar"] [data-baseweb="select"] * {color:#0E1B24 !important;}
.side-brand {display:flex; align-items:center; gap:12px; margin-bottom:6px;}
.side-brand img {width:44px; height:44px;}
.side-brand b {font-family:'Bricolage Grotesque', sans-serif; font-size:1.05rem; line-height:1.15; color:#fff;}

/* ── bandeau d'accueil ── */
.hero {background:linear-gradient(90deg, rgba(9,20,27,.94) 0%, rgba(9,20,27,.62) 100%), url('__HEROBG__') center/cover;
  border-radius:14px; padding:22px 28px; display:flex; align-items:center; gap:20px; margin-bottom:18px;
  flex-wrap:wrap; border-bottom:3px solid __COPPER__;}
.hero img.lg {width:68px; height:68px;}
.hero h1 {margin:0; padding:0; color:#fff; font-size:1.75rem; line-height:1.1;}
.hero p {margin:4px 0 0; color:#a9bec8; font-size:.98rem;}
.chips {margin-left:auto; display:flex; gap:12px; flex-wrap:wrap;}
.chip {background:rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.16); border-radius:8px;
  padding:8px 16px; color:#a9bec8; font-size:.8rem; min-width:110px;}
.chip b {display:block; color:#fff; font-size:1.35rem; font-family:'Bricolage Grotesque', sans-serif;}
.chip.alert b {color:#ff8a8f;}

/* ── cartes KPI ── */
.kpi {background:#fff; border:1px solid #dde5e9; border-radius:10px; padding:14px 18px; display:flex;
  align-items:center; gap:14px; margin-bottom:14px; position:relative; overflow:hidden;}
.kpi:before {content:""; position:absolute; left:0; right:0; bottom:0; height:3px; background:var(--c);}
.kpi .ico {flex:none; width:54px; height:54px; border-radius:12px; display:flex; align-items:center;
  justify-content:center; background:#F3F6F8;}
.kpi .ico img {width:38px; height:38px; object-fit:contain;}
.kpi .l {font-size:.85rem; color:#5b6f7a; font-weight:500;}
.kpi .v {font-size:1.85rem; font-weight:700; color:#0E1B24; line-height:1.15; white-space:nowrap;}
.kpi .d {font-size:.8rem; color:#7a8d97;}

/* ── bandeaux d'alerte ── */
.alert {display:flex; align-items:center; gap:16px; border-radius:12px; padding:14px 20px; margin-bottom:18px;}
.alert.crit {background:linear-gradient(90deg,#3a0d12,#5c1319); border:1px solid #e5484d; color:#ffdcde;}
.alert.ok {background:#e8f7f4; border:1px solid #9fdcd3; color:#12564f;}
.alert .dot {flex:none; width:14px; height:14px; border-radius:50%; background:#ff4d55; animation:pulse 1.7s infinite;}
.alert.ok .dot {background:__TEAL__; animation:none;}
.alert b {font-family:'Bricolage Grotesque', sans-serif; font-size:1.12rem; color:#fff;}
.alert.ok b {color:#0b3f3a;}
.alert .sub {font-size:.9rem; opacity:.9; margin-top:2px;}
@keyframes pulse {0% {box-shadow:0 0 0 0 rgba(255,77,85,.7);} 70% {box-shadow:0 0 0 14px rgba(255,77,85,0);}
  100% {box-shadow:0 0 0 0 rgba(255,77,85,0);}}
@media (prefers-reduced-motion: reduce) {.alert .dot {animation:none;}}
.riskpill {display:inline-block; padding:2px 10px; border-radius:20px; font-size:.78rem; font-weight:600;}

/* ── titres de section, onglets, graphiques ── */
.sec {display:flex; align-items:center; gap:10px; margin:6px 0 14px;}
.sec img {width:32px; height:32px; object-fit:contain;}
.sec h3 {margin:0; padding:0; color:#0E1B24;}
.stTabs [data-baseweb="tab"] {font-weight:600;}
[data-testid="stPlotlyChart"] {background:#fff; border:1px solid #dde5e9; border-radius:10px; padding:6px;}
[data-testid="stForm"] {background:#fff; border:1px solid #dde5e9; border-radius:12px;}
</style>
"""

CSS_LOGIN = """
<style>
.stApp {background:linear-gradient(rgba(9,20,27,.25), rgba(9,20,27,.25)), url('__LOGINBG__') center/cover fixed;}
.login-brand {text-align:center; margin-bottom:16px;}
.login-brand img {width:96px; height:96px; filter:drop-shadow(0 8px 22px rgba(0,0,0,.45));}
.login-brand h1 {margin:10px 0 0; padding:0; color:#fff; font-size:1.9rem; line-height:1.15;}
.login-brand p {margin:4px 0 0; color:#a9bec8;}
[data-testid="stForm"] {background:rgba(255,255,255,.97); border:none; border-radius:14px; padding:1.4rem 1.4rem .8rem;
  box-shadow:0 20px 50px rgba(0,0,0,.4);}
.login-note {text-align:center; color:#a9bec8; font-size:.85rem; margin-top:12px;}
.login-note b {color:#fff;}
</style>
"""

for _k, _v in {"__TILE__": asset_uri("bg_tile.png"), "__INK__": INK, "__COPPER__": COPPER, "__TEAL__": TEAL,
               "__HEROBG__": asset_uri("bg_hero.jpg"), "__LOGINBG__": asset_uri("bg_login.jpg")}.items():
    CSS = CSS.replace(_k, _v)
    CSS_LOGIN = CSS_LOGIN.replace(_k, _v)

st.markdown(CSS, unsafe_allow_html=True)

RTL_CSS = """<style>
[data-testid="stAppViewContainer"], [data-testid="stSidebar"], [data-testid="stForm"] {direction:rtl;}
[data-testid="stPlotlyChart"], [data-testid="stDataFrame"], .stCode, code {direction:ltr; text-align:left;}
.kpi, .alert, .sec, .hero {direction:rtl;} .chips {margin-left:0; margin-right:auto;}
.alert, .kpi, .sec {text-align:right;}
</style>"""

DARK_CSS = """<style>
.stApp {background-color:#0b141a !important; background-image:none !important;}
.stApp, .stApp p, .stApp label, .stApp li, .stApp span, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5,
.stApp [data-testid="stMetricValue"], .stApp [data-testid="stMetricLabel"], .stApp [data-testid="stCaptionContainer"],
.stApp .stMarkdown {color:#e3edf1;}
.stApp [data-baseweb="input"] *, .stApp [data-baseweb="select"] *, .stApp [data-baseweb="textarea"] * {color:#0E1B24 !important;}
.kpi, .ws-big div, .ws-card {background:#13222c !important; border-color:#27424f !important;}
.kpi .v, .kpi .l, .kpi .d {color:#e3edf1 !important;} .kpi .ico {background:#1c3340 !important;}
.sec h3 {color:#fff !important;}
[data-testid="stPlotlyChart"], [data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"] {background:#13222c !important; border-color:#27424f !important;}
.stTabs [data-baseweb="tab"] {color:#b8cbd3;}
.alert.ok {background:#0f2f2c; border-color:#1d6b63; color:#bfeee8;} .alert.ok b {color:#e6fbf8;}
</style>"""
st.markdown(RTL_CSS if LANG == "ar" else "", unsafe_allow_html=True)


# ───────────────────────── HELPERS ─────────────────────────
def show(fig, height=380):
    """Affiche un graphique plotly (compatible anciennes/nouvelles versions de Streamlit)."""
    fig.update_layout(template="plotly_dark" if DARK else "plotly_white", height=height,
                      margin=dict(l=10, r=10, t=50, b=10),
                      font=dict(family="Instrument Sans, Segoe UI, sans-serif", color="#dbe7ec" if DARK else "#27404d"),
                      title_font=dict(family="Bricolage Grotesque, Segoe UI, sans-serif", size=17,
                                      color="#ffffff" if DARK else INK),
                      colorway=[COPPER, TEAL, BLUE, AMBER, RED])
    if DARK:
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    if STREAMLIT_NEW:
        st.plotly_chart(fig, width="stretch")
    else:
        st.plotly_chart(fig, use_container_width=True)


def show_df(df, **kw):
    if STREAMLIT_NEW:
        st.dataframe(df, width="stretch", **kw)
    else:
        st.dataframe(df, use_container_width=True, **kw)


def kpi(col, label, value, delta="", color=BLUE, icon=None):
    img = f"<img src='{icon_uri(icon)}'/>" if icon else ""
    col.markdown(f"<div class='kpi' style='--c:{color}; --t:{color}22'><div class='ico'>{img}</div>"
                 f"<div><div class='l'>{label}</div><div class='v'>{value}</div>"
                 f"<div class='d'>{delta}&nbsp;</div></div></div>", unsafe_allow_html=True)


def section(title, icon):
    st.markdown(f"<div class='sec'><img src='{icon_uri(icon)}'/><h3>{title}</h3></div>",
                unsafe_allow_html=True)


def sha(p):
    return hashlib.sha256(p.encode()).hexdigest()


# Identifiant (en minuscules) -> empreinte SHA-256 du mot de passe (le mot de passe n'est pas écrit en clair)
DEFAULT_USERS = {"ezzouhra": "1150a5655cd0a7841f5b883e3e39772e8aafc6b5481ab84bf50f256c5fe20345"}


def get_users():
    """Utilisateurs : st.secrets['users'] si défini, sinon le compte par défaut."""
    try:
        if "users" in st.secrets:
            return {str(k).lower(): sha(str(v)) for k, v in st.secrets["users"].items()}
    except Exception:
        pass
    return DEFAULT_USERS


def load_raw():
    path = LIVE_CSV if os.path.exists(LIVE_CSV) else SOURCE_CSV
    return pd.read_csv(path, encoding="utf-8-sig")


def save_raw(df):
    try:
        df.to_csv(LIVE_CSV, index=False)
    except Exception:
        pass   # système de fichiers en lecture seule : on garde la session


def enrich(raw):
    d = raw.copy()
    d = d.rename(columns={"Air temperature [K]": "air_temp", "Process temperature [K]": "process_temp",
                          "Rotational speed [rpm]": "rpm", "Torque [Nm]": "torque",
                          "Tool wear [min]": "tool_wear", "Machine failure": "failure",
                          "Product ID": "product_id", "Type": "type"})
    d["air_temp_c"] = d["air_temp"] - 273.15
    d["process_temp_c"] = d["process_temp"] - 273.15
    d["temp_diff"] = d["process_temp"] - d["air_temp"]
    d["power_kw"] = d["torque"] * d["rpm"] * 2 * np.pi / 60 / 1000
    d["status"] = np.where(d["failure"] == 1, "Panne", "Normal")

    def ftype(r):
        t = [n for c, n in MODES.items() if r[c] == 1]
        return " + ".join(t) if t else (T("mode_unclassified") if r["failure"] == 1 else T("mode_none"))
    d["failure_type"] = d.apply(ftype, axis=1)
    return d


# ───────────────────────── RISQUE DE PANNE IMMINENTE ─────────────────────────
CRIT, HIGH, WATCH = 85, 60, 40          # seuils du score de risque (0-100)
RISK_LABEL = {k: T("cause_" + k) for k in ("wear", "osf", "hdf", "pwf")}
RISK_ACTION = {k: T("action_" + k) for k in ("wear", "osf", "hdf", "pwf")}
OSF_LIMIT = {"L": 11000, "M": 12000, "H": 13000}   # limite couple × usure (min·Nm) selon la qualité


def add_risk(d):
    """Ajoute risk (0-100) et risk_cause : proximité des 4 seuils de panne du dataset AI4I."""
    def c(x):
        return np.clip(x, 0, 1)
    pw = d["power_kw"] * 1000
    lim = d["type"].map(OSF_LIMIT)
    r = pd.DataFrame({
        "wear": c((d["tool_wear"] - 190) / 35),
        "osf": c((d["torque"] * d["tool_wear"] / lim - 0.88) / 0.12),
        "hdf": c((9.2 - d["temp_diff"]) / 0.6) * c((1440 - d["rpm"]) / 60),
        "pwf": np.maximum(c((3900 - pw) / 400), c((pw - 8700) / 400)),
    })
    d = d.copy()
    for k in r:
        d["r_" + k] = (r[k] * 100).round(0)
    d["risk"] = (r.max(axis=1) * 100).round(0)
    d["risk_cause"] = r.idxmax(axis=1)
    return d


def risk_level(score):
    return T("lvl_crit") if score >= CRIT else T("lvl_high") if score >= HIGH else T("lvl_watch") if score >= WATCH else T("lvl_ok")


# ───────────────────────── SCHÉMA DE LA MACHINE ─────────────────────────
ZONE_FLAG = {"wear": "TWF", "osf": "OSF", "hdf": "HDF", "pwf": "PWF"}
ZONE_NAME = {k: T("zone_" + k) for k in ("wear", "osf", "hdf", "pwf")}


def zone_color(v):
    return RED if v >= CRIT else COPPER if v >= HIGH else AMBER if v >= WATCH else TEAL


def zone_scores(row):
    """Score de chaque zone ; 100 si la panne correspondante est déjà constatée."""
    out = {}
    for k, flag in ZONE_FLAG.items():
        out[k] = 100.0 if (row.failure == 1 and row[flag] == 1) else float(row["r_" + k])
    return out


def zone_info(row, k):
    pw = row.power_kw * 1000
    lim = OSF_LIMIT[row.type]

    def fmt(x):
        return f"{x:,.0f}".replace(",", " ")
    short = {"wear": T("zi_wear", v=int(row.tool_wear)), "osf": T("zi_osf", v=f"{row.torque:.1f}"),
             "hdf": T("zi_hdf", v=f"{row.temp_diff:.1f}"),
             "pwf": T("zi_pwf", rpm=int(row.rpm), kw=f"{pw / 1000:.1f}")}[k]
    why = {"wear": T("why_wear", v=int(row.tool_wear)),
           "osf": T("why_osf", v=fmt(row.torque * row.tool_wear), q=row.type, lim=fmt(lim)),
           "hdf": T("why_hdf", dt=f"{row.temp_diff:.1f}", rpm=int(row.rpm)),
           "pwf": T("why_pwf", w=fmt(pw))}[k]
    return short, why


def _gear_pts(cx, cy, r, teeth=10):
    pts, step = [], 2 * np.pi / teeth
    for i in range(teeth):
        c, w = i * step + step / 2, step * .5
        for ang, rr in ((c - w * .8, r * .8), (c - w * .5, r), (c + w * .5, r), (c + w * .8, r * .8)):
            pts.append(f"{cx + rr * np.cos(ang):.1f},{cy + rr * np.sin(ang):.1f}")
    return " ".join(pts)


def machine_svg(row):
    zr = zone_scores(row)
    worst = max(zr, key=zr.get)
    has_issue = zr[worst] >= WATCH
    failed = row.failure == 1
    parts = []

    def zone(x, y, w, h, k):
        c, hot = zone_color(zr[k]), (k == worst and zr[k] >= WATCH)
        cls = ' class="pulse"' if hot else ""
        short, _ = zone_info(row, k)
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{c}" fill-opacity=".14" '
                     f'stroke="{c}" stroke-width="{3.5 if hot else 1.5}"{cls}/>')
        parts.append(f'<text x="{x + 14}" y="{y + 27}" fill="#fff" font-size="14" font-weight="700">{ZONE_NAME[k]}</text>')
        parts.append(f'<text x="{x + 14}" y="{y + 46}" fill="{c}" font-size="12.5">{short}</text>')
        parts.append(f'<rect x="{x + w - 52}" y="{y + 10}" width="42" height="21" rx="10" fill="{c}"/>'
                     f'<text x="{x + w - 31}" y="{y + 25}" text-anchor="middle" fill="#0E1B24" font-size="12" '
                     f'font-weight="700">{int(zr[k])}%</text>')
        if hot:
            parts.append(f'<g class="pulse"><circle cx="{x}" cy="{y}" r="15" fill="{c}"/>'
                         f'<text x="{x}" y="{y + 6}" text-anchor="middle" fill="#0E1B24" font-size="18" '
                         f'font-weight="800">!</text></g>')

    # fond, sol, tuyaux
    parts.append('<rect width="900" height="490" rx="18" fill="#0E1B24"/>')
    parts.append('<rect x="60" y="380" width="780" height="34" rx="8" fill="#1d3340"/>')
    parts.append('<path d="M400 155V200M742 155V200" stroke="#4a6a7a" stroke-width="6" fill="none"/>')
    # zones
    zone(100, 200, 200, 170, "pwf")
    zone(330, 200, 140, 170, "osf")
    zone(655, 200, 175, 170, "wear")
    zone(330, 40, 500, 115, "hdf")
    # pièces mécaniques
    parts.append(f'<polygon points="{_gear_pts(200, 308, 48)}" fill="#3b5565" stroke="#6d8a99" stroke-width="2"/>'
                 '<circle cx="200" cy="308" r="17" fill="#0E1B24"/>'
                 '<rect x="300" y="300" width="32" height="16" fill="#6d8a99"/>')
    parts.append('<circle cx="400" cy="308" r="42" fill="#2b4857" stroke="#8aa6b4" stroke-width="3"/>'
                 '<circle cx="400" cy="308" r="13" fill="#0E1B24"/>')
    for a in (90, 210, 330):
        ca, sa = np.cos(np.radians(a)), np.sin(np.radians(a))
        parts.append(f'<line x1="{400 + 13 * ca:.1f}" y1="{308 + 13 * sa:.1f}" x2="{400 + 38 * ca:.1f}" '
                     f'y2="{308 + 38 * sa:.1f}" stroke="#8aa6b4" stroke-width="8" stroke-linecap="round"/>')
    parts.append('<rect x="470" y="291" width="190" height="34" rx="4" fill="#9fb4bf"/>'
                 '<rect x="470" y="297" width="190" height="4" fill="#cfdde4"/>'
                 '<rect x="735" y="278" width="80" height="60" rx="6" fill="#3b5565"/>'
                 '<polygon points="735,288 676,308 735,328" fill="#dfe8ec"/>')
    parts.append('<circle cx="392" cy="122" r="24" fill="none" stroke="#6d8a99" stroke-width="3"/>')
    for a in (0, 120, 240):
        ca, sa = np.cos(np.radians(a)), np.sin(np.radians(a))
        parts.append(f'<line x1="392" y1="122" x2="{392 + 20 * ca:.1f}" y2="{122 + 20 * sa:.1f}" stroke="#6d8a99" '
                     'stroke-width="6" stroke-linecap="round"/>')
    for i in range(8):
        parts.append(f'<line x1="{470 + i * 42}" y1="100" x2="{470 + i * 42}" y2="142" stroke="#4a6a7a" '
                     'stroke-width="5" stroke-linecap="round"/>')
    # en-tête : identifiant + statut
    if failed:
        st_txt, st_col = T("svg_failed"), RED
    elif zr[worst] >= CRIT:
        st_txt, st_col = T("svg_imminent"), RED
    elif zr[worst] >= HIGH:
        st_txt, st_col = T("svg_watch"), COPPER
    elif zr[worst] >= WATCH:
        st_txt, st_col = T("svg_vigilance"), AMBER
    else:
        st_txt, st_col = T("svg_normal"), TEAL
    parts.append(f'<text x="100" y="78" fill="#fff" font-size="26" font-weight="800">{row.product_id}</text>'
                 f'<text x="100" y="102" fill="#8aa6b4" font-size="14">{T("quality")} {row.type}</text>'
                 f'<rect x="100" y="116" width="170" height="28" rx="14" fill="{st_col}"/>'
                 f'<text x="185" y="135" text-anchor="middle" fill="#0E1B24" font-size="13" '
                 f'font-weight="800">{st_txt}</text>')
    # message du bas
    if has_issue:
        msg, mc = T("svg_problem", zone=ZONE_NAME[worst], action=RISK_ACTION[worst]), zone_color(zr[worst])
    elif failed:
        msg, mc = T("svg_failed_unclass"), RED
    else:
        msg, mc = T("svg_none"), TEAL
    parts.append(f'<text x="100" y="446" fill="{mc}" font-size="18" font-weight="700">{msg}</text>')
    lx = 100
    for lab, col in ((T("lvl_ok"), TEAL), (T("lvl_watch"), AMBER), (T("lvl_high"), COPPER), (T("lvl_crit"), RED)):
        parts.append(f'<circle cx="{lx}" cy="472" r="5" fill="{col}"/>'
                     f'<text x="{lx + 12}" y="476" fill="#8aa6b4" font-size="12">{lab}</text>')
        lx += 110
    style = ('<style>.pulse{animation:blink 1.4s ease-in-out infinite}'
             '@keyframes blink{0%,100%{opacity:1}50%{opacity:.35}}'
             '@media (prefers-reduced-motion:reduce){.pulse{animation:none}}</style>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 490" '
            'font-family="Segoe UI, Arial, sans-serif">' + style + "".join(parts) + "</svg>")


# ───────────────────────── LOGIN ─────────────────────────
def _set_lang():
    st.session_state.lang = st.session_state.lang_w


def _set_dark():
    st.session_state.dark = st.session_state.dark_w


def lang_picker():
    st.radio(T("language"), list(LANGS), index=list(LANGS).index(LANG), format_func=LANGS.get,
             key="lang_w", on_change=_set_lang, horizontal=True)


def login_page():
    st.markdown(CSS_LOGIN, unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.1, 1])
    with mid:
        st.markdown("<div style='height:6vh'></div>", unsafe_allow_html=True)
        st.markdown(f"<div class='login-brand'><img src='{LOGO_URI}'/><h1>{APP_NAME}</h1>"
                    f"<p>{T('tagline')}</p></div>", unsafe_allow_html=True)
        with st.form("login"):
            st.markdown(f"#### {T('login_title')}")
            user = st.text_input(T("user_id"))
            pwd = st.text_input(T("password"), type="password")
            ok = st.form_submit_button(T("login_btn"), type="primary")
        if ok:
            users = get_users()
            if user.strip().lower() in users and users[user.strip().lower()] == sha(pwd):
                st.session_state.auth = True
                st.session_state.user = user.strip()
                st.session_state.welcome = True
                st.rerun()
            else:
                st.error(T("login_err"))
        lang_picker()
        st.markdown(f"<div class='login-note'>{T('restricted')} · {APP_NAME}</div>", unsafe_allow_html=True)


if not st.session_state.get("auth"):
    login_page()
    st.stop()

if DARK:
    st.markdown(DARK_CSS, unsafe_allow_html=True)

# ───────────────────────── DATA (session) ─────────────────────────
if "raw" not in st.session_state:
    st.session_state.raw = load_raw()

raw = st.session_state.raw
data = add_risk(enrich(raw))
at_risk = data[(data.failure == 0) & (data.risk >= WATCH)].sort_values("risk", ascending=False)
n_crit = int((at_risk.risk >= CRIT).sum())
n_high = int(((at_risk.risk >= HIGH) & (at_risk.risk < CRIT)).sum())


def render_machine(row):
    """Schéma de la machine + diagnostic (utilisé par Inspection et par la page QR)."""
    zr = zone_scores(row)
    left, right = st.columns([2.1, 1])
    with left:
        b64 = base64.b64encode(machine_svg(row).encode("utf-8")).decode()
        st.markdown(f"<img src='data:image/svg+xml;base64,{b64}' style='width:100%; border-radius:16px; "
                    "box-shadow:0 6px 24px rgba(14,27,36,.18)'/>", unsafe_allow_html=True)
    with right:
        m1, m2 = st.columns(2)
        m1.metric(T("speed"), f"{int(row.rpm)} rpm")
        m2.metric(T("torque"), f"{row.torque:.1f} Nm")
        m1.metric(T("wear"), f"{int(row.tool_wear)} min")
        m2.metric(T("temp_gap"), f"{row.temp_diff:.1f} K")
        st.markdown(f"##### {T('diagnostic')}")
        issues = [k for k in sorted(zr, key=zr.get, reverse=True) if zr[k] >= WATCH]
        if not issues:
            st.success(T("no_issue"))
        for k in issues:
            col = zone_color(zr[k])
            st.markdown(f"<span class='riskpill' style='background:{col}22; color:{col}'>"
                        f"{ZONE_NAME[k]} · {int(zr[k])}%</span>", unsafe_allow_html=True)
            st.write(zone_info(row, k)[1])
            st.caption(T("advice", a=RISK_ACTION[k]))


def svg_html(row):
    b64 = base64.b64encode(machine_svg(row).encode("utf-8")).decode()
    st.markdown(f"<img src='data:image/svg+xml;base64,{b64}' style='width:100%; border-radius:16px'/>",
                unsafe_allow_html=True)


ctx = SimpleNamespace(
    T=T, lang=LANG, dark=DARK, data=data, raw=raw, at_risk=at_risk, CRIT=CRIT, HIGH=HIGH, WATCH=WATCH,
    RED=RED, COPPER=COPPER, TEAL=TEAL, BLUE=BLUE, AMBER=AMBER, section=section, kpi=kpi, show=show,
    show_df=show_df, svg_html=svg_html, zone_scores=zone_scores, zone_name=lambda k: ZONE_NAME[k],
    zone_color=zone_color, action_label=lambda k: RISK_ACTION[k], ZONE_FLAG=ZONE_FLAG, enrich=enrich,
    add_risk=add_risk, save_raw=save_raw, load_raw=load_raw, app_name=APP_NAME, logo_uri=LOGO_URI,
    tagline_for=lambda lang: tr("tagline", lang))

# ───────────────────────── SIDEBAR : FILTRES ─────────────────────────
with st.sidebar:
    st.markdown(f"<div class='side-brand'><img src='{LOGO_URI}'/><b>{APP_NAME}</b></div>",
                unsafe_allow_html=True)
    st.markdown(T("connected", u=st.session_state.user))
    if st.button(T("logout")):
        keep = {k: st.session_state[k] for k in ("lang", "dark") if k in st.session_state}
        st.session_state.clear()
        st.session_state.update(keep)
        st.rerun()
    lang_picker()
    st.toggle(T("dark_mode"), value=DARK, key="dark_w", on_change=_set_dark)
    if st.button(T("workshop_btn")):
        st.session_state.workshop = True
        st.rerun()
    st.markdown("---")
    st.markdown(f"### {T('filters')}")
    f_type = st.multiselect(T("f_quality"), ["L", "M", "H"], default=["L", "M", "H"])
    f_status = st.multiselect(T("f_status"), ["Normal", "Panne"], default=["Normal", "Panne"])
    causes = list(MODES.values())
    f_cause = st.multiselect(T("f_cause"), causes)
    rpm_min, rpm_max = int(data.rpm.min()), int(data.rpm.max())
    f_rpm = st.slider(T("f_rpm"), rpm_min, rpm_max, (rpm_min, rpm_max))
    t_min, t_max = float(data.torque.min()), float(data.torque.max())
    f_tq = st.slider(T("f_torque"), t_min, t_max, (t_min, t_max))
    w_min, w_max = int(data.tool_wear.min()), int(data.tool_wear.max())
    f_wear = st.slider(T("f_wear"), w_min, w_max, (w_min, w_max))

df = data[data.type.isin(f_type) & data.status.isin(f_status)
          & data.rpm.between(*f_rpm) & data.torque.between(*f_tq) & data.tool_wear.between(*f_wear)]
if f_cause:
    df = df[df.failure_type.apply(lambda s: any(c in s for c in f_cause))]

# ───────────────────────── MODE ÉCRAN ATELIER ─────────────────────────
if st.session_state.get("workshop"):
    extras.render_workshop(ctx)
    st.stop()

# ───────────────────────── HEADER ─────────────────────────
if st.session_state.get("flash"):
    st.toast(st.session_state.pop("flash"))
if st.session_state.get("save_error"):
    st.warning("⚠️ Sauvegarde impossible : " + st.session_state.pop("save_error")
               + " — les données restent en mémoire pour cette session seulement.")
if st.session_state.pop("welcome", False):
    st.toast(T("welcome", u=st.session_state.user))
    if n_crit:
        st.toast(T("toast_crit", n=n_crit), icon="🚨")

_nf_all = int(data.failure.sum())
st.markdown(
    f"<div class='hero'><img class='lg' src='{LOGO_URI}'/><div><h1>{APP_NAME}</h1><p>{T('tagline')}</p></div>"
    f"<div class='chips'><div class='chip'>{T('chip_machines')}<b>{len(data):,}</b></div>"
    f"<div class='chip alert'>{T('chip_failures')}<b>{_nf_all:,}</b></div>"
    f"<div class='chip'>{T('chip_rate')}<b>{data.failure.mean() * 100:.2f}%</b></div>"
    f"<div class='chip alert'>{T('chip_crit')}<b>{n_crit}</b></div></div></div>",
    unsafe_allow_html=True)

# Page ouverte depuis un QR code : ?machine=ID
_qm = str(st.query_params.get("machine", "")).strip().upper()
if _qm:
    with st.container(border=True):
        _hit = data[data.product_id.str.upper() == _qm]
        if _hit.empty:
            st.warning(T("id_not_found") + f" ({_qm})")
        else:
            st.markdown(f"#### {T('qr_machine_page', id=_qm)}")
            render_machine(_hit.iloc[0])
        if st.button(T("close")):
            st.query_params.clear()
            st.rerun()

(tab_dash, tab_alert, tab_insp, tab_map, tab_maint, tab_rep, tab_notif,
 tab_an, tab_add, tab_data) = st.tabs(
    [T("tab_dash"), f"{T('tab_alert')} ({n_crit})" if n_crit else T("tab_alert"), T("tab_insp"), T("tab_map"),
     T("tab_maint"), T("tab_reports"), T("tab_notif"), T("tab_an"), T("tab_add"), T("tab_data")])


# ═════════════════════ DASHBOARD ═════════════════════
def alert_banner():
    if n_crit:
        top = at_risk.head(3)
        ids = " · ".join(f"{r.product_id} ({RISK_LABEL[r.risk_cause]}, {int(r.risk)}%)" for r in top.itertuples())
        st.markdown(f"<div class='alert crit'><div class='dot'></div><div><b>{T('banner_crit', n=n_crit)}</b>"
                    f"<div class='sub'>{T('banner_top', ids=ids)}</div></div></div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='alert ok'><div class='dot'></div><div><b>{T('banner_ok')}</b>"
                    f"<div class='sub'>{T('banner_ok_sub')}</div></div></div>", unsafe_allow_html=True)


with tab_dash:
    alert_banner()
    section(T("sec_dash"), "chart")
    if df.empty:
        st.warning(T("no_data_filters"))
    else:
        n, nf = len(df), int(df.failure.sum())
        glob_rate = data.failure.mean() * 100
        rate = nf / n * 100
        c = st.columns(3) + st.columns(3)   # 2 lignes de 3 KPI
        kpi(c[0], T("chip_machines"), f"{n:,}", T("d_of_total", n=f"{len(data):,}"), BLUE, "machines")
        kpi(c[1], T("failures"), f"{nf:,}", T("d_failing"), RED, "engine")
        kpi(c[2], T("fail_rate"), f"{rate:.2f}%", T("d_global", r=f"{glob_rate:.2f}"),
            RED if rate > glob_rate else TEAL, "chart")
        kpi(c[3], T("avg_wear"), f"{df.tool_wear.mean():.0f} min", T("d_tool"), COPPER, "tools")
        kpi(c[4], T("avg_speed"), f"{df.rpm.mean():.0f} rpm", T("d_rotation"), TEAL, "speed")
        kpi(c[5], T("avg_torque"), f"{df.torque.mean():.1f} Nm", T("d_dtemp", v=f"{df.temp_diff.mean():.1f}"),
            AMBER, "tools")
        st.markdown("")

        a, b = st.columns(2)
        with a:
            cnt = df.status.value_counts().reset_index()
            cnt.columns = ["status", "n"]
            fig = px.pie(cnt, names="status", values="n", hole=.55, color="status",
                         color_discrete_map=COLORS, title=T("ch_status"))
            show(fig)
        with b:
            r = df.groupby("type")["failure"].mean().mul(100).reindex(["L", "M", "H"]).dropna().reset_index()
            fig = px.bar(r, x="type", y="failure", text=r["failure"].round(2).astype(str) + "%",
                         color="type", title=T("ch_rate_q"),
                         color_discrete_sequence=[RED, COPPER, BLUE],
                         labels={"failure": T("lbl_rate"), "type": T("quality")})
            fig.update_layout(showlegend=False)
            show(fig)

        a, b = st.columns(2)
        with a:
            cause = df[df.failure == 1].failure_type.value_counts().sort_values().reset_index()
            cause.columns = ["cause", "n"]
            fig = px.bar(cause, x="n", y="cause", orientation="h", title=T("ch_causes"),
                         color="n", color_continuous_scale="Oranges", text="n")
            fig.update_layout(coloraxis_showscale=False)
            show(fig)
        with b:
            bins = pd.cut(df.tool_wear, bins=list(range(0, 271, 30)), include_lowest=True)
            w = df.groupby(bins, observed=True)["failure"].mean().mul(100).reset_index()
            w["tool_wear"] = w["tool_wear"].astype(str)
            fig = px.line(w, x="tool_wear", y="failure", markers=True, title=T("ch_wear_rate"),
                          labels={"failure": T("lbl_rate"), "tool_wear": T("wear")})
            fig.update_traces(line_color=COPPER, line_width=3)
            show(fig)

        samp = df.sample(min(len(df), 4000), random_state=1)
        fig = px.scatter(samp, x="rpm", y="torque", color="status", color_discrete_map=COLORS,
                         hover_data=["product_id", "type", "tool_wear", "failure_type"], opacity=.65,
                         title=T("ch_scatter"))
        show(fig, 450)

# ═════════════════════ ALERTES ═════════════════════
with tab_alert:
    section(T("sec_alert"), "engine")
    st.caption(T("alert_caption"))
    alert_banner()
    healthy = (len(data) - len(at_risk)) / len(data) * 100
    c1, c2, c3 = st.columns(3)
    kpi(c1, T("lvl_crit"), f"{n_crit}", T("d_score_ge", v=CRIT), RED, "engine")
    kpi(c2, T("lvl_high"), f"{n_high}", T("d_score_range", a=HIGH, b=CRIT - 1), COPPER, "tools")
    kpi(c3, T("kpi_healthy"), f"{healthy:.1f}%", T("d_healthy"), TEAL, "speed")

    if at_risk.empty:
        st.success(T("no_watch"))
    else:
        a, b = st.columns([1, 1])
        with a:
            gauge = px.bar(at_risk.assign(niveau=at_risk.risk.map(risk_level)).groupby(["risk_cause", "niveau"])
                           .size().reset_index(name="n").assign(cause=lambda x: x.risk_cause.map(RISK_LABEL)),
                           x="n", y="cause", color="niveau", orientation="h", title=T("ch_by_cause"),
                           color_discrete_map={T("lvl_crit"): RED, T("lvl_high"): COPPER, T("lvl_watch"): AMBER},
                           labels={"n": T("machines"), "cause": ""})
            show(gauge, 340)
        with b:
            hist = px.histogram(at_risk, x="risk", nbins=24, title=T("ch_score_hist"),
                                color_discrete_sequence=[COPPER], labels={"risk": T("score")})
            hist.add_vline(x=CRIT, line_dash="dash", line_color=RED, annotation_text=T("lvl_crit").lower())
            show(hist, 340)

        thr = st.radio(T("show_label"), [CRIT, HIGH, WATCH], horizontal=True, index=1,
                       format_func=lambda x: {CRIT: T("opt_crit"), HIGH: T("opt_crit_high"), WATCH: T("opt_all")}[x])
        view = at_risk[at_risk.risk >= thr].head(50)
        tab = pd.DataFrame({
            T("machine"): view.product_id, T("quality"): view.type, T("score"): view.risk.astype(int),
            T("level"): view.risk.map(risk_level), T("probable_cause"): view.risk_cause.map(RISK_LABEL),
            T("action"): view.risk_cause.map(RISK_ACTION),
            T("wear"): view.tool_wear, T("torque"): view.torque, "rpm": view.rpm})
        show_df(tab, hide_index=True, column_config={
            T("score"): st.column_config.ProgressColumn(T("score"), min_value=0, max_value=100, format="%d")})
        st.caption(T("view_caption", n=len(view)))
        st.download_button(T("dl_alerts"), tab.to_csv(index=False).encode("utf-8"),
                           "alertes_machines.csv", "text/csv")

# ═════════════════════ INSPECTION MACHINE ═════════════════════
with tab_insp:
    section(T("sec_insp"), "machines")
    st.caption(T("insp_caption"))
    mode = st.radio("m", ["risk", "failed", "id"], horizontal=True, label_visibility="collapsed",
                    format_func=lambda x: T("mode_" + x))
    if mode == "risk":
        pool = at_risk.head(300)
    elif mode == "failed":
        pool = data[data.failure == 1].sort_values("UDI", ascending=False).head(300)
    else:
        pid = st.text_input(T("id_input")).strip().upper()
        pool = data[data.product_id.str.upper() == pid] if pid else data.iloc[0:0]
        if pid and pool.empty:
            st.warning(T("id_not_found"))

    if pool.empty:
        if mode != "id":
            st.info(T("none_list"))
    else:
        scores = dict(zip(pool.product_id, pool.risk))
        pick = st.selectbox(T("machine"), pool.product_id.tolist(),
                            format_func=lambda p: T("risk_fmt", p=p, s=int(scores[p])))
        render_machine(pool[pool.product_id == pick].iloc[0])

# ═════════════════════ CARTE DE L'USINE ═════════════════════
with tab_map:
    extras.render_map(ctx)

# ═════════════════════ MAINTENANCE (planning, historique, coûts, comparaison) ═════════════════════
with tab_maint:
    s_board, s_plan, s_hist, s_cost, s_cmp = st.tabs([T("sub_board"), T("sub_plan"), T("sub_hist"), T("sub_cost"), T("sub_cmp")])
    with s_board:
        extras.render_board(ctx)
    with s_plan:
        extras.render_planning(ctx)
    with s_hist:
        extras.render_history(ctx)
    with s_cost:
        extras.render_costs(ctx)
    with s_cmp:
        extras.render_compare(ctx)

# ═════════════════════ RAPPORTS / IMPORT / QR ═════════════════════
with tab_rep:
    extras.render_reports(ctx)

# ═════════════════════ NOTIFICATIONS ═════════════════════
with tab_notif:
    extras.render_notif(ctx)

# ═════════════════════ ANALYSE ═════════════════════
with tab_an:
    section(T("sec_an"), "speed")
    if df.empty:
        st.warning(T("no_data_filters"))
    else:
        a, b = st.columns(2)
        with a:
            var = st.selectbox(T("an_var"), ["rpm", "torque", "tool_wear", "air_temp_c",
                                              "process_temp_c", "temp_diff", "power_kw"])
            fig = px.histogram(df, x=var, color="status", color_discrete_map=COLORS, nbins=40,
                               barmode="overlay", opacity=.7, marginal="box",
                               title=T("an_dist", v=var))
            show(fig, 450)
        with b:
            num = ["air_temp_c", "process_temp_c", "rpm", "torque", "tool_wear", "power_kw", "failure"]
            corr = df[num].corr().round(2)
            fig = px.imshow(corr, text_auto=True, color_continuous_scale="RdBu_r", zmin=-1, zmax=1,
                            title=T("an_corr"))
            show(fig, 450)

        a, b = st.columns(2)
        with a:
            fail = df[df.failure == 1]
            if len(fail):
                fig = px.sunburst(fail, path=["type", "failure_type"], title=T("an_sun"),
                                  color_discrete_sequence=[COPPER, TEAL, BLUE, AMBER, RED])
                show(fig, 420)
            else:
                st.info(T("no_failures_sel"))
        with b:
            fig = px.box(df, x="type", y="tool_wear", color="status", color_discrete_map=COLORS,
                         category_orders={"type": ["L", "M", "H"]}, title=T("an_box"))
            show(fig, 420)

        samp = df.sample(min(len(df), 3000), random_state=2)
        fig = px.scatter_3d(samp, x="rpm", y="torque", z="tool_wear", color="status",
                            color_discrete_map=COLORS, opacity=.7, title=T("an_3d"))
        fig.update_traces(marker_size=3)
        show(fig, 550)

# ═════════════════════ SAISIE ═════════════════════
with tab_add:
    section(T("sec_add"), "iot")
    st.caption(T("add_caption"))
    with st.form("add_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        t = c1.selectbox(T("quality_prod"), ["L", "M", "H"])
        air = c1.number_input(T("air_temp"), 290.0, 310.0, 300.0, 0.1)
        proc = c1.number_input(T("proc_temp"), 300.0, 320.0, 310.0, 0.1)
        rpm = c2.number_input(T("speed_rot"), 1000, 3000, 1500, 10)
        tq = c2.number_input(T("torque") + " (Nm)", 3.0, 80.0, 40.0, 0.1)
        wear = c2.number_input(T("wear"), 0, 300, 100, 1)
        c3.markdown(f"**{T('failures_seen')}**")
        flags = {k: c3.checkbox(f"{k} — {v}") for k, v in MODES.items()}
        submit = st.form_submit_button(T("save_measure"), type="primary")

    if submit:
        new_id = int(raw["UDI"].max()) + 1
        any_fail = int(any(flags.values()))
        row = {"UDI": new_id, "Product ID": f"{t}{new_id + 40000}", "Type": t,
               "Air temperature [K]": air, "Process temperature [K]": proc,
               "Rotational speed [rpm]": rpm, "Torque [Nm]": tq, "Tool wear [min]": wear,
               "Machine failure": any_fail, **{k: int(v) for k, v in flags.items()}}
        st.session_state.raw = pd.concat([raw, pd.DataFrame([row])], ignore_index=True)
        save_raw(st.session_state.raw)
        new = add_risk(enrich(pd.DataFrame([row]))).iloc[0]
        extras.log_measurement(row["Product ID"], rpm, tq, wear, air, proc, int(new.risk))
        st.session_state.flash = T("flash_added", id=row["Product ID"])
        if not any_fail and new.risk >= HIGH:
            st.session_state.flash += " " + T("flash_risk", lvl=risk_level(new.risk).lower(), s=int(new.risk),
                                              cause=RISK_LABEL[new.risk_cause].lower())
        if not any_fail and new.risk >= CRIT:
            sent = extras.auto_send(ctx, add_risk(enrich(pd.DataFrame([row]))))
            if sent:
                st.session_state.flash += " " + sent
        st.rerun()

    st.markdown(f"##### {T('last_entries')}")
    last = enrich(st.session_state.raw).tail(8).iloc[::-1]
    show_df(last[["UDI", "product_id", "type", "air_temp", "process_temp", "rpm", "torque",
                  "tool_wear", "status", "failure_type"]], hide_index=True)

    if len(st.session_state.raw) > 10000:
        if st.button(T("reset_btn")):
            st.session_state.raw = pd.read_csv(SOURCE_CSV, encoding="utf-8-sig")
            if os.path.exists(LIVE_CSV):
                os.remove(LIVE_CSV)
            st.rerun()

# ═════════════════════ DONNÉES ═════════════════════
with tab_data:
    section(T("sec_data"), "machines")
    st.write(T("n_rows", n=f"{len(df):,}"))
    show_df(df.drop(columns=["air_temp_c", "process_temp_c"]).head(1000), hide_index=True)
    st.download_button(T("dl_csv"), df.to_csv(index=False).encode("utf-8"),
                       "donnees_filtrees.csv", "text/csv")
