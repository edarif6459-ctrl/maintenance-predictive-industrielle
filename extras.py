"""Maintenix — fonctionnalités de gestion : planning, historique, coûts, comparaison,
rapports, import, QR codes, alertes Email/Telegram, carte de l'usine, mode écran atelier."""
import datetime as dt
import os

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import notify
import reports
from i18n import tr

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TASKS_CSV = os.path.join(BASE_DIR, "tasks.csv")
HIST_CSV = os.path.join(BASE_DIR, "history.csv")
TASK_COLS = ["id", "machine", "task", "owner", "due", "status", "prio"]
HIST_COLS = ["machine", "ts", "rpm", "torque", "wear", "air", "proc", "risk"]
STATUSES = ["todo", "doing", "done"]
RAW_FLAGS = ["TWF", "HDF", "PWF", "OSF", "RNF"]
IMPORT_REQUIRED = ["Type", "Air temperature [K]", "Process temperature [K]", "Rotational speed [rpm]",
                   "Torque [Nm]", "Tool wear [min]"]

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Africa/Casablanca")
except Exception:
    TZ = None


def now():
    return dt.datetime.now(TZ) if TZ else dt.datetime.now()


def _read_csv(path, cols):
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception:
        df = pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df[cols].copy()


def _write_csv(df, path):
    """Écriture atomique (fichier temporaire puis remplacement) : pas de CSV corrompu en cas de coupure."""
    try:
        tmp = path + ".tmp"
        df.to_csv(tmp, index=False)
        os.replace(tmp, path)
        return True
    except Exception as e:
        st.session_state["save_error"] = f"{os.path.basename(path)} : {type(e).__name__}"
        return False   # disque en lecture seule : on garde la session


def _secret(name):
    try:
        return st.secrets[name]
    except Exception:
        return None


def clamp(v, lo, hi):
    return float(min(max(float(v), lo), hi))


def level_key(ctx, score):
    return "crit" if score >= ctx.CRIT else "high" if score >= ctx.HIGH else "watch" if score >= ctx.WATCH else "ok"


def raw_rows(typ, air, proc, rpm, tq, wears):
    """DataFrame au format brut AI4I (pour réutiliser enrich + add_risk)."""
    wears = list(wears)
    d = {"UDI": 0, "Product ID": "X", "Type": typ, "Air temperature [K]": air, "Process temperature [K]": proc,
         "Rotational speed [rpm]": rpm, "Torque [Nm]": tq, "Tool wear [min]": wears, "Machine failure": 0}
    d.update({f: 0 for f in RAW_FLAGS})
    return pd.DataFrame(d)


def machine_input(ctx, label_key, default, key):
    pid = st.text_input(ctx.T(label_key), value=default, key=key).strip().upper()
    hit = ctx.data[ctx.data.product_id.str.upper() == pid]
    if pid and hit.empty:
        st.warning(ctx.T("id_not_found"))
    return None if hit.empty else hit.iloc[0]


def default_ids(ctx, n=2):
    ids = ctx.at_risk.product_id.head(n).tolist() + ctx.data.product_id.head(n).tolist()
    return (ids + ["", ""])[:n]


# ═════════════════════ 6. PLANNING ═════════════════════
def get_tasks():
    if "tasks" not in st.session_state:
        st.session_state.tasks = _read_csv(TASKS_CSV, TASK_COLS)
    return st.session_state.tasks


def set_tasks(df):
    st.session_state.tasks = df.reset_index(drop=True)
    _write_csv(st.session_state.tasks, TASKS_CSV)


def add_tasks(rows):
    tasks = get_tasks()
    m = pd.to_numeric(tasks["id"], errors="coerce").max()
    nid = 1 if pd.isna(m) else int(m) + 1
    new = [{"id": str(nid + i), **r} for i, r in enumerate(rows)]
    set_tasks(pd.concat([tasks, pd.DataFrame(new)], ignore_index=True))


def render_planning(ctx):
    T = ctx.T
    ctx.section(T("plan_title"), "tools")
    with st.form("task_form", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([1, 2, 1, 1])
        machine = c1.text_input(T("machine_id"))
        title = c2.text_input(T("task"))
        owner = c3.text_input(T("owner"))
        due = c4.date_input(T("due"), value=now().date())
        ok = st.form_submit_button(T("add_task"), type="primary")
    if ok:
        if title.strip():
            add_tasks([{"machine": machine.strip().upper(), "task": title.strip(), "owner": owner.strip(),
                        "due": str(due), "status": "todo"}])
            st.rerun()
        else:
            st.warning(T("task_required"))

    crit = ctx.at_risk[ctx.at_risk.risk >= ctx.CRIT].head(20)
    if st.button(T("auto_tasks", n=len(crit)), disabled=crit.empty):
        tasks = get_tasks()
        open_ids = set(tasks[tasks.status != "done"].machine)
        rows = [{"machine": r.product_id, "task": f"{ctx.action_label(r.risk_cause)} ({int(r.risk)}%)",
                 "owner": "", "due": str(now().date() + dt.timedelta(days=2)), "status": "todo"}
                for r in crit.itertuples() if r.product_id not in open_ids]
        if rows:
            add_tasks(rows)
        st.session_state.flash = T("tasks_created", n=len(rows))
        st.rerun()

    tasks = get_tasks()
    today = str(now().date())
    for col, (i, s) in zip(st.columns(3), enumerate(STATUSES)):
        sub = tasks[tasks.status == s]
        col.markdown(f"##### {T('st_' + s)} ({len(sub)})")
        for r in sub.itertuples():
            with col.container(border=True):
                late = " ⚠️" if (s != "done" and r.due and r.due < today) else ""
                st.markdown(f"**{r.machine or '—'}** · {r.task}")
                st.caption(f"👤 {r.owner or '—'} · 📅 {r.due}{late}")
                b1, b2, b3 = st.columns([2, 2, 1])
                if i > 0 and b1.button(f"◀ {T('st_' + STATUSES[i - 1])}", key=f"prev_{r.id}"):
                    tasks.loc[tasks.id == r.id, "status"] = STATUSES[i - 1]
                    set_tasks(tasks)
                    st.rerun()
                if i < 2 and b2.button(f"{T('st_' + STATUSES[i + 1])} ▶", key=f"next_{r.id}"):
                    tasks.loc[tasks.id == r.id, "status"] = STATUSES[i + 1]
                    set_tasks(tasks)
                    st.rerun()
                if b3.button("🗑", key=f"del_{r.id}"):
                    set_tasks(tasks[tasks.id != r.id])
                    st.rerun()
    if not len(tasks):
        st.info(T("no_tasks"))
    st.caption(T("persist_note"))


# ═════════════════════ 5b. TABLEAU MAINTENIX (machines, tâches, alertes Telegram / Email) ═════════════════════
OPERATORS = ["Sara", "Ahmed", "Mohamed", "Khadija"]
MACHINE_KINDS = ["CNC Mill", "Lathe Machine", "Hydraulic Press", "Robotic Arm"]
PRIO = {"low": ("prio_low", "#2e9e6b"), "normal": ("prio_normal", "#6c7a86"), "high": ("prio_high", "#dc3545")}
STATUS_LABEL = {"todo": "st_todo", "doing": "st_doing", "done": "st_done"}
BOARD_CSS = """<style>
.mx-wrap {background:#fff; border:1px solid #dde5e9; border-radius:10px; overflow-x:auto; margin-bottom:14px;}
.mx-head {background:#1d2329; color:#fff; padding:12px 18px; font-weight:600; border-radius:10px 10px 0 0;}
.mx-t {width:100%; border-collapse:collapse; font-size:.92rem; color:#1d2b33;}
.mx-t th {padding:10px 12px; border:1px solid #dde5e9; text-align:center; background:#fff; font-weight:700;}
.mx-t td {padding:10px 12px; border:1px solid #dde5e9; text-align:center;}
.mx-t tbody tr:nth-child(odd) td {background:#f1f3f4;}
.mx-b {display:inline-block; padding:2px 10px; border-radius:6px; color:#fff; font-size:.75rem; font-weight:700;}
.mx-cap {font-size:.8rem; color:#6b7f8a; margin:-6px 0 12px;}
</style>"""


def _h(x):
    return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _badge(text, color):
    return f"<span class='mx-b' style='background:{color}'>{_h(text)}</span>"


def _machine_table(ctx):
    """Quelques machines du dataset : les plus à risque + quelques machines saines."""
    d = ctx.data
    risky = d[(d.failure == 0) & (d.risk >= ctx.WATCH)].sort_values("risk", ascending=False).head(5)
    healthy = d[(d.failure == 0) & (d.risk < ctx.WATCH)].head(3)
    import zlib
    rows = []
    last = {}
    tasks = get_tasks()
    for r in tasks[tasks.status == "done"].itertuples():
        if r.due:
            last[r.machine] = max(last.get(r.machine, ""), r.due)
    for r in get_hist().itertuples():
        last[r.machine] = max(last.get(r.machine, ""), str(r.ts)[:10])
    for r in pd.concat([risky, healthy]).itertuples():
        h = zlib.crc32(r.product_id.encode())
        crit = r.risk >= ctx.CRIT
        warn = r.risk >= ctx.HIGH
        rows.append({"id": r.product_id, "name": f"{MACHINE_KINDS[h % 4]} {'ABCD'[(h // 4) % 4]}",
                     "lvl": "crit" if crit else "warn" if warn else "ok", "temp": round(r.process_temp_c, 1),
                     "vib": round(0.5 + 4.0 * r.risk / 100, 1), "last": last.get(r.product_id, "—"),
                     "op": OPERATORS[h % 4], "risk": int(r.risk), "cause": r.risk_cause})
    return rows


def _machine_message(ctx, m):
    T = ctx.T
    return (f"🚨 {ctx.app_name}\n{T('machine')} : {m['id']} — {m['name']}\n"
            f"{T('mx_status')} : {T('mx_' + m['lvl'])} ({m['risk']}%)\n"
            f"{T('cause_' + m['cause'])} → {T('action_' + m['cause'])}\n{T('mx_operator')} : {m['op']}")


def render_board(ctx):
    T = ctx.T
    st.markdown(BOARD_CSS, unsafe_allow_html=True)
    for kind, text in st.session_state.pop("notif_msgs", []):
        getattr(st, kind)(text)
    machines = _machine_table(ctx)
    colors = {"crit": "#dc3545", "warn": "#f2b134", "ok": "#198754"}
    head = [T("mx_id"), T("mx_name"), T("mx_status"), T("mx_temp"), T("mx_vib"), T("mx_last"), T("mx_operator")]
    body = "".join(
        f"<tr><td>{_h(m['id'])}</td><td>{_h(m['name'])}</td><td>{_badge(T('mx_' + m['lvl']), colors[m['lvl']])}</td>"
        f"<td>{m['temp']}</td><td>{m['vib']}</td><td>{_h(m['last'])}</td><td>{_h(m['op'])}</td></tr>" for m in machines)
    st.markdown(f"<div class='mx-wrap'><div class='mx-head'>{T('mx_table')}</div>"
                f"<table class='mx-t'><thead><tr>{''.join(f'<th>{_h(x)}</th>' for x in head)}</tr></thead>"
                f"<tbody>{body}</tbody></table></div><div class='mx-cap'>{T('mx_note')}</div>", unsafe_allow_html=True)
    labels = {m["id"]: f"{m['id']} - {m['name']}" for m in machines}
    ids = list(labels)

    left, right = st.columns(2)
    with left:
        with st.form("mx_task_form", clear_on_submit=True):
            st.markdown(f"**{T('mx_add_task')}**")
            title = st.text_input(T("mx_task_title"), placeholder=T("mx_task_ph"))
            mid = st.selectbox(T("machine"), ids, format_func=labels.get)
            due = st.date_input(T("mx_due"), value=now().date(), format="DD/MM/YYYY")
            prio = st.selectbox(T("mx_prio"), list(PRIO), index=1, format_func=lambda k: T(PRIO[k][0]))
            ok = st.form_submit_button(T("mx_save_plan"), type="primary", use_container_width=True)
        if ok:
            if title.strip():
                op = next(m["op"] for m in machines if m["id"] == mid)
                add_tasks([{"machine": mid, "task": title.strip(), "owner": op, "due": str(due),
                            "status": "todo", "prio": prio}])
                st.session_state.flash = T("mx_saved")
                st.rerun()
            else:
                st.warning(T("task_required"))
    with right:
        tasks = get_tasks().copy()
        tasks = tasks.sort_values("due") if len(tasks) else tasks
        rows = "".join(
            f"<tr><td>{_h(r.task)}</td><td>{_h(r.due)}</td>"
            f"<td>{_badge(T(PRIO.get(r.prio, PRIO['normal'])[0]), PRIO.get(r.prio, PRIO['normal'])[1])}</td>"
            f"<td>{T(STATUS_LABEL.get(r.status, 'st_todo'))}</td></tr>" for r in tasks.head(12).itertuples())
        empty = "" if rows else f"<tr><td colspan='4'>{T('no_tasks')}</td></tr>"
        st.markdown(f"<div class='mx-wrap'><div class='mx-head' style='background:#0dcaf0;color:#04323a'>{T('mx_planning')}</div>"
                    f"<table class='mx-t'><thead><tr><th>{T('task')}</th><th>{T('due')}</th><th>{T('mx_prio')}</th>"
                    f"<th>{T('mx_status')}</th></tr></thead><tbody>{rows}{empty}</tbody></table></div>",
                    unsafe_allow_html=True)

    import urllib.parse as up
    em, tg = channels()
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown(f"### :blue[{T('mx_tg_title')}]")
            pick = st.selectbox(T("mx_pick"), ids, format_func=labels.get, key="mx_tg_pick")
            m1 = next(x for x in machines if x["id"] == pick)
            st.caption(f"{T('mx_operator')} : {m1['op']}")
            tg_url = "https://t.me/share/url?url=&text=" + up.quote(_machine_message(ctx, m1))
            st.link_button(T("mx_tg_open"), tg_url, type="primary", use_container_width=True)
            st.caption(T("mx_tg_hint"))
            with st.expander(T("mx_auto_title")):
                chat = st.text_input("chat_id", value=str((tg or {}).get("chat_id", "")), key="mx_tg_chat")
                if st.button(T("mx_tg_send"), key="mx_tg_btn", disabled=not tg):
                    ok, msg = notify.send_telegram({**tg, "chat_id": chat}, _machine_message(ctx, m1))
                    (st.success if ok else st.error)("Telegram : OK" if ok else msg)
                if not tg:
                    st.info(T("mx_tg_missing"))
    with c2:
        with st.container(border=True):
            st.markdown(f"### :green[{T('mx_em_title')}]")
            to = st.text_input(T("mx_em_to"), value="", key="mx_em_to", placeholder="operateur@exemple.com")
            pick2 = st.selectbox(T("mx_pick"), ids, format_func=labels.get, key="mx_em_pick")
            m2 = next(x for x in machines if x["id"] == pick2)
            st.caption(f"{T('mx_operator')} : {m2['op']}")
            subject = f"{ctx.app_name} — {m2['id']} ({T('mx_' + m2['lvl'])})"
            valid = "@" in to and "." in to.split("@")[-1]
            url = ("https://mail.google.com/mail/?view=cm&fs=1&to=" + up.quote(to.strip()) + "&su=" + up.quote(subject)
                   + "&body=" + up.quote(_machine_message(ctx, m2)))
            st.link_button(T("mx_em_open"), url, type="primary", use_container_width=True, disabled=not valid)
            st.caption(T("mx_gmail_hint"))
            with st.expander(T("mx_auto_title")):
                if em:
                    if st.button(T("mx_em_send"), key="mx_em_btn", disabled=not valid):
                        ok, msg = notify.send_email({**em, "to": to}, subject, _machine_message(ctx, m2))
                        (st.success if ok else st.error)(f"Email : OK → {msg}" if ok else msg)
                else:
                    st.markdown(T("quick_help"))
                    code = st.text_input(T("quick_code"), type="password", key="quick_code", placeholder="abcd efgh ijkl mnop")
                    if st.button(T("quick_btn"), key="quick_btn"):
                        if not code.strip():
                            st.warning(T("cfg_missing"))
                            st.stop()
                        cfg = {"host": "smtp.gmail.com", "port": 587, "user": DEFAULT_GMAIL, "password": code,
                               "to": DEFAULT_GMAIL}
                        ok, msg = notify.send_email(cfg, f"{ctx.app_name} — test", T("alert_test", app=ctx.app_name))
                        if ok:
                            notify.save_settings(email=cfg)
                            _flash("success", f"Email : OK → {msg}")
                            st.rerun()
                        else:
                            st.error(msg)


# ═════════════════════ 7. HISTORIQUE ═════════════════════
def get_hist():
    if "hist" not in st.session_state:
        st.session_state.hist = _read_csv(HIST_CSV, HIST_COLS)
    return st.session_state.hist


def render_history(ctx):
    T = ctx.T
    ctx.section(T("hist_title"), "chart")
    row = machine_input(ctx, "machine_id", default_ids(ctx, 1)[0], "hist_pid")
    if row is None:
        return
    pid = row.product_id
    m = st.columns(4)
    m[0].metric(T("speed"), f"{int(row.rpm)} rpm")
    m[1].metric(T("torque"), f"{row.torque:.1f} Nm")
    m[2].metric(T("wear"), f"{int(row.tool_wear)} min")
    m[3].metric(T("risk_score"), f"{int(row.risk)}%")

    # courbe de risque selon l'usure (trajectoire estimée)
    wears = list(range(0, 301, 5))
    proj = ctx.add_risk(ctx.enrich(raw_rows(row.type, row.air_temp, row.process_temp, row.rpm, row.torque, wears)))
    fig = go.Figure(go.Scatter(x=wears, y=proj.risk, mode="lines", line=dict(color=ctx.COPPER, width=3), name=T("risk_score")))
    fig.add_hline(y=ctx.CRIT, line_dash="dash", line_color=ctx.RED, annotation_text=T("lvl_crit"))
    fig.add_hline(y=ctx.HIGH, line_dash="dot", line_color=ctx.COPPER, annotation_text=T("lvl_high"))
    fig.add_trace(go.Scatter(x=[row.tool_wear], y=[row.risk], mode="markers", name=T("current_point"),
                             marker=dict(size=14, color=ctx.RED, line=dict(width=2, color="#fff"))))
    fig.update_layout(title=T("proj_title"), xaxis_title=T("wear"), yaxis_title=T("risk_score"), yaxis_range=[0, 105])
    ctx.show(fig, 360)
    st.caption(T("proj_note"))

    # mesures enregistrées dans le temps
    hist = get_hist()
    h = hist[hist.machine == pid].copy()
    st.markdown(f"##### {T('hist_log')}")
    if h.empty:
        st.info(T("hist_empty"))
    else:
        h["ts"] = pd.to_datetime(h["ts"], errors="coerce")
        for c in ("rpm", "torque", "wear", "risk"):
            h[c] = pd.to_numeric(h[c], errors="coerce")
        h = h.sort_values("ts")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=h.ts, y=h.risk, mode="lines+markers", name=T("risk_score"),
                                 line=dict(color=ctx.RED, width=3)))
        fig.add_trace(go.Scatter(x=h.ts, y=h.wear, mode="lines+markers", name=T("wear"), yaxis="y2",
                                 line=dict(color=ctx.TEAL, width=3)))
        fig.update_layout(title=T("hist_chart"), yaxis=dict(title=T("risk_score"), range=[0, 105]),
                          yaxis2=dict(title=T("wear"), overlaying="y", side="right"))
        ctx.show(fig, 360)
        ctx.show_df(h.sort_values("ts", ascending=False)[["ts", "rpm", "torque", "wear", "risk"]], hide_index=True)

    with st.form("hist_form", clear_on_submit=False):
        st.markdown(f"**{T('hist_add')}**")
        c = st.columns(5)
        air = c[0].number_input(T("air_temp"), 290.0, 310.0, clamp(round(row.air_temp, 1), 290.0, 310.0), 0.1)
        proc = c[1].number_input(T("proc_temp"), 300.0, 320.0, clamp(round(row.process_temp, 1), 300.0, 320.0), 0.1)
        rpm = c[2].number_input(T("speed"), 1000, 3000, int(clamp(row.rpm, 1000, 3000)), 10)
        tq = c[3].number_input(T("torque"), 3.0, 80.0, clamp(round(row.torque, 1), 3.0, 80.0), 0.1)
        wear = c[4].number_input(T("wear"), 0, 300, int(clamp(row.tool_wear, 0, 300)), 1)
        ok = st.form_submit_button(T("hist_save"), type="primary")
    if ok:
        score = float(ctx.add_risk(ctx.enrich(raw_rows(row.type, air, proc, rpm, tq, [wear]))).risk.iloc[0])
        new = pd.DataFrame([{"machine": pid, "ts": now().strftime("%Y-%m-%d %H:%M:%S"), "rpm": rpm, "torque": tq,
                             "wear": wear, "air": air, "proc": proc, "risk": int(score)}])
        st.session_state.hist = pd.concat([hist, new.astype(str)], ignore_index=True)
        _write_csv(st.session_state.hist, HIST_CSV)
        st.session_state.flash = T("hist_saved", id=pid)
        st.rerun()


# ═════════════════════ 8. COÛTS ET GAINS ═════════════════════
def money(v, cur):
    return f"{v:,.0f}".replace(",", " ") + f" {cur}"


def render_costs(ctx):
    T = ctx.T
    ctx.section(T("cost_title"), "tools")
    st.caption(T("cost_help"))
    c = st.columns(4)
    cur = c[0].selectbox(T("currency"), ["MAD", "EUR", "USD"])
    cost_fail = c[1].number_input(T("cost_fail"), 0, 10_000_000, 50_000, 1000)
    cost_prev = c[2].number_input(T("cost_prev"), 0, 10_000_000, 5_000, 500)
    eff = c[3].slider(T("effectiveness"), 0, 100, 80)
    scope = st.radio(T("cost_scope"), [ctx.CRIT, ctx.HIGH],
                     format_func=lambda x: T("scope_crit") if x == ctx.CRIT else T("scope_high"), horizontal=True)

    grp = ctx.data[ctx.data.risk >= scope]
    p = float(grp.failure.mean()) if len(grp) else 0.0          # taux de panne observé dans ce groupe
    n_t = int(((ctx.data.risk >= scope) & (ctx.data.failure == 0)).sum())   # machines encore en marche
    n_f = int(ctx.data.failure.sum())
    loss_seen = n_f * cost_fail
    no_action = n_t * p * cost_fail
    prev_total = n_t * cost_prev
    residual = n_t * p * (1 - eff / 100) * cost_fail
    avoided = n_t * p * eff / 100
    net = no_action - (prev_total + residual)

    k = st.columns(4)
    ctx.kpi(k[0], T("loss_seen"), money(loss_seen, cur), T("n_failures", n=n_f), ctx.RED, "engine")
    ctx.kpi(k[1], T("prev_cost"), money(prev_total, cur), T("n_machines", n=n_t), ctx.COPPER, "tools")
    ctx.kpi(k[2], T("avoided"), f"{avoided:.1f}", T("p_obs", p=f"{p * 100:.0f}"), ctx.TEAL, "speed")
    ctx.kpi(k[3], T("net_gain"), money(net, cur), T("roi", r=f"{(net / prev_total * 100) if prev_total else 0:.0f}"),
            ctx.TEAL if net >= 0 else ctx.RED, "chart")

    fig = go.Figure()
    fig.add_bar(x=[T("scn_without"), T("scn_with")], y=[no_action, residual], name=T("scn_loss"), marker_color=ctx.RED)
    fig.add_bar(x=[T("scn_without"), T("scn_with")], y=[0, prev_total], name=T("scn_prev"), marker_color=ctx.TEAL)
    fig.update_layout(barmode="stack", title=T("cost_chart", cur=cur), yaxis_title=cur)
    ctx.show(fig, 380)
    st.caption(T("cost_formula"))


# ═════════════════════ 9. COMPARAISON ═════════════════════
def render_compare(ctx):
    T = ctx.T
    ctx.section(T("cmp_title"), "machines")
    d1, d2 = default_ids(ctx, 2)
    a, b = st.columns(2)
    with a:
        r1 = machine_input(ctx, "machine_a", d1, "cmp_a")
    with b:
        r2 = machine_input(ctx, "machine_b", d2, "cmp_b")
    if r1 is None or r2 is None:
        st.info(T("cmp_pick"))
        return
    for col, r in ((a, r1), (b, r2)):
        with col:
            ctx.svg_html(r)
    zones = list(ctx.ZONE_FLAG)
    names = [ctx.zone_name(k) for k in zones]
    fig = go.Figure()
    for r, colr in ((r1, ctx.COPPER), (r2, ctx.TEAL)):
        zs = ctx.zone_scores(r)
        fig.add_trace(go.Scatterpolar(r=[zs[k] for k in zones] + [zs[zones[0]]], theta=names + [names[0]],
                                      fill="toself", name=r.product_id, line_color=colr, opacity=.75))
    fig.update_layout(title=T("cmp_radar"), polar=dict(radialaxis=dict(range=[0, 100])))
    x1, x2 = st.columns(2)
    with x1:
        ctx.show(fig, 420)
    metrics = [("speed", "rpm"), ("torque", "torque"), ("wear", "tool_wear"), ("temp_diff", "temp_diff"),
               ("power_kw", "power_kw"), ("risk_score", "risk")]
    tab = pd.DataFrame({T("indicator"): [T(k) for k, _ in metrics],
                        r1.product_id: [round(float(r1[c]), 2) for _, c in metrics],
                        r2.product_id: [round(float(r2[c]), 2) for _, c in metrics]})
    # barres normalisées (% du maximum du parc) pour comparer des unités différentes
    norm = {c: float(ctx.data[c].max()) or 1.0 for _, c in metrics}
    fig2 = go.Figure()
    for r, colr in ((r1, ctx.COPPER), (r2, ctx.TEAL)):
        fig2.add_bar(x=[T(k) for k, _ in metrics], y=[float(r[c]) / norm[c] * 100 for _, c in metrics],
                     name=r.product_id, marker_color=colr)
    fig2.update_layout(barmode="group", title=T("cmp_bars"), yaxis_title="% max")
    with x2:
        ctx.show(fig2, 420)
    ctx.show_df(tab, hide_index=True)


# ═════════════════════ 10-12. RAPPORTS, IMPORT, QR ═════════════════════
def make_reports(ctx, n_top):
    lang = ctx.lang if ctx.lang != "ar" else "fr"      # le PDF n'embarque pas de police arabe
    TL = lambda k, **kw: tr(k, lang, **kw)
    d, ar = ctx.data, ctx.at_risk
    n_crit = int((ar.risk >= ctx.CRIT).sum())
    n_high = int(((ar.risk >= ctx.HIGH) & (ar.risk < ctx.CRIT)).sum())
    kp = [(TL("machines"), f"{len(d):,}".replace(",", " ")), (TL("failures"), f"{int(d.failure.sum()):,}".replace(",", " ")),
          (TL("fail_rate"), f"{d.failure.mean() * 100:.2f}%"), (TL("lvl_crit"), n_crit),
          (TL("lvl_high"), n_high), (TL("avg_wear"), f"{d.tool_wear.mean():.0f} min")]
    top = ar.head(n_top)
    header = [TL("machine"), TL("quality"), TL("score"), TL("level"), TL("probable_cause"), TL("action"),
              TL("wear"), TL("torque")]
    rows = [[r.product_id, r.type, int(r.risk), TL("lvl_" + level_key(ctx, r.risk)), TL("cause_" + r.risk_cause),
             TL("action_" + r.risk_cause), int(r.tool_wear), f"{r.torque:.1f}"] for r in top.itertuples()]
    pdf = reports.build_pdf(ctx.app_name, f"{TL('report_name')} · {ctx.tagline_for(lang)}", kp,
                            TL("top_risky", n=len(rows)), header, rows, risk_col=2, footer=ctx.app_name)

    T = ctx.T
    sx = pd.DataFrame({T("indicator"): [k for k, _ in kp], T("value"): [str(v) for _, v in kp]})
    risk_df = pd.DataFrame({T("machine"): ar.product_id, T("quality"): ar.type, T("score"): ar.risk.astype(int),
                            T("level"): ar.risk.map(lambda s: T("lvl_" + level_key(ctx, s))),
                            T("probable_cause"): ar.risk_cause.map(lambda k: T("cause_" + k)),
                            T("action"): ar.risk_cause.map(lambda k: T("action_" + k)),
                            T("wear"): ar.tool_wear, T("torque"): ar.torque, "rpm": ar.rpm}).head(500)
    fail_df = d[d.failure == 1][["product_id", "type", "rpm", "torque", "tool_wear", "failure_type"]].tail(500)
    sheets = {T("sheet_summary"): sx, T("sheet_risk"): risk_df, T("sheet_failures"): fail_df}
    tasks = get_tasks()
    if len(tasks):
        sheets[T("sheet_tasks")] = tasks.rename(columns={"machine": T("machine"), "task": T("task"),
                                                         "owner": T("owner"), "due": T("due"), "status": T("status")})
    return {"pdf": pdf, "xlsx": reports.build_excel(sheets)}


def normalize_import(df, raw):
    """Retourne (df_au_format_brut, nb_lignes_ignorées, message_erreur)."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in IMPORT_REQUIRED if c not in df.columns]
    if missing:
        return None, 0, ", ".join(missing)
    n0 = len(df)
    num = IMPORT_REQUIRED[1:]
    for c in num:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["Type"] = df["Type"].astype(str).str.strip().str.upper()
    df = df[df["Type"].isin(["L", "M", "H"])].dropna(subset=num).reset_index(drop=True)
    skipped = n0 - len(df)
    if df.empty:
        return None, skipped, "0"
    for f in RAW_FLAGS:
        df[f] = pd.to_numeric(df[f], errors="coerce").fillna(0).astype(int) if f in df.columns else 0
    df["Machine failure"] = (pd.to_numeric(df["Machine failure"], errors="coerce").fillna(0).astype(int)
                             if "Machine failure" in df.columns else 0)
    df["Machine failure"] = np.maximum(df["Machine failure"], df[RAW_FLAGS].max(axis=1))
    start = int(raw["UDI"].max()) + 1
    df["UDI"] = range(start, start + len(df))
    pid = df["Product ID"].astype(str).str.strip() if "Product ID" in df.columns else pd.Series([""] * len(df))
    df["Product ID"] = [p if p and p.lower() != "nan" else f"{t}{u + 40000}"
                        for p, t, u in zip(pid, df["Type"], df["UDI"])]
    return df[list(raw.columns)], skipped, None


def render_import(ctx):
    T = ctx.T
    ctx.section(T("import_title"), "iot")
    st.caption(T("import_help"))
    tpl = pd.DataFrame({"Type": ["L", "M"], "Air temperature [K]": [300.1, 298.4], "Process temperature [K]": [310.2, 308.9],
                        "Rotational speed [rpm]": [1500, 1620], "Torque [Nm]": [42.5, 36.0], "Tool wear [min]": [120, 210]})
    st.download_button(T("dl_template"), tpl.to_csv(index=False).encode("utf-8"), "modele_import.csv", "text/csv")
    up = st.file_uploader(T("upload"), type=["csv", "xlsx", "xls"], key=f"up_{st.session_state.get('up_n', 0)}")
    if not up:
        return
    try:
        df = pd.read_csv(up, sep=None, engine="python", encoding="utf-8-sig") if up.name.lower().endswith(".csv") \
            else pd.read_excel(up)
    except Exception as e:
        st.error(f"{T('import_unreadable')} ({type(e).__name__})")
        return
    new, skipped, err = normalize_import(df, ctx.raw)
    if err is not None:
        st.error(T("import_missing", cols=err))
        return
    st.success(T("import_ready", n=len(new)) + (f" {T('import_skipped', n=skipped)}" if skipped else ""))
    ctx.show_df(new.head(10), hide_index=True)
    if st.button(T("import_btn", n=len(new)), type="primary"):
        st.session_state.raw = pd.concat([ctx.raw, new], ignore_index=True)
        ctx.save_raw(st.session_state.raw)
        scored = ctx.add_risk(ctx.enrich(new))
        crit_new = scored[(scored.failure == 0) & (scored.risk >= ctx.CRIT)]
        msg = T("import_done", n=len(new))
        if len(crit_new):
            msg += " " + T("import_crit", n=len(crit_new))
            sent = auto_send(ctx, crit_new.sort_values("risk", ascending=False))
            if sent:
                msg += " " + sent
        st.session_state.flash = msg
        st.session_state.up_n = st.session_state.get("up_n", 0) + 1
        st.rerun()


def render_qr(ctx):
    T = ctx.T
    ctx.section(T("qr_title"), "machines")
    st.caption(T("qr_help"))
    default_url = st.session_state.get("app_url") or _secret("APP_URL") or ""
    base = st.text_input(T("app_url"), value=default_url, placeholder="https://mon-app.streamlit.app").strip()
    st.session_state.app_url = base
    if not base:
        st.info(T("qr_need_url"))
        return
    pid = st.text_input(T("machine_id"), value=default_ids(ctx, 1)[0], key="qr_pid").strip().upper()
    link = f"{base.rstrip('/')}/?machine={pid}"
    png = reports.make_qr_png(link)
    if png is None:
        st.error(T("qr_missing_lib"))
        return
    a, b = st.columns([1, 2])
    a.image(png, width=220)
    b.code(link)
    b.download_button(T("dl_qr"), png, f"qr_{pid}.png", "image/png")
    st.markdown("---")
    n = st.slider(T("qr_sheet_n"), 3, 60, 12, 3)
    if st.button(T("qr_sheet_btn")):
        items = [(i, f"{base.rstrip('/')}/?machine={i}") for i in ctx.at_risk.product_id.head(n)]
        st.session_state.qr_sheet = reports.qr_sheet_pdf(items, f"{ctx.app_name} — QR")
    if st.session_state.get("qr_sheet"):
        st.download_button(T("dl_qr_sheet"), st.session_state.qr_sheet, "qr_machines.pdf", "application/pdf")


def render_reports(ctx):
    T = ctx.T
    t_rep, t_imp, t_qr = st.tabs([T("sub_report"), T("sub_import"), T("sub_qr")])
    with t_rep:
        ctx.section(T("report_title"), "chart")
        st.caption(T("report_help"))
        if ctx.lang == "ar":
            st.info(T("pdf_ar_note"))
        n_top = st.slider(T("top_n"), 5, 50, 15)
        if st.button(T("prepare"), type="primary"):
            st.session_state.report_files = make_reports(ctx, n_top)
        files = st.session_state.get("report_files")
        if files:
            c1, c2 = st.columns(2)
            stamp = now().strftime("%Y%m%d_%H%M")
            c1.download_button(T("dl_pdf"), files["pdf"], f"maintenix_rapport_{stamp}.pdf", "application/pdf")
            c2.download_button(T("dl_xlsx"), files["xlsx"], f"maintenix_rapport_{stamp}.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with t_imp:
        render_import(ctx)
    with t_qr:
        render_qr(ctx)


# ═════════════════════ 13. ALERTES EMAIL / TELEGRAM ═════════════════════
DEFAULT_GMAIL = "ezzouhradarif25@gmail.com"   # adresse pré-remplie (modifiable)

SECRETS_EXAMPLE = '''APP_URL = "https://mon-app.streamlit.app"

[email]
host = "smtp.gmail.com"
port = 587
user = "mon.adresse@gmail.com"
password = "mot-de-passe-application"
to = "responsable@exemple.com,autre@exemple.com"

[telegram]
token = "123456:ABC-DEF..."
chat_id = "123456789"
'''


def channels():
    """(email, telegram) : settings.json > secrets > variables d'environnement / .env."""
    return notify.get_config({"email": _secret("email"), "telegram": _secret("telegram")})


def alert_text(ctx, rows):
    T = ctx.T
    lines = [T("alert_head", n=len(rows), app=ctx.app_name)]
    for r in rows.head(15).itertuples():
        lines.append(f"• {r.product_id} — {T('cause_' + r.risk_cause)} — {int(r.risk)}% — {T('action_' + r.risk_cause)}")
    if len(rows) > 15:
        lines.append(T("alert_more", n=len(rows) - 15))
    return "\n".join(lines)


def send_all(ctx, subject, text):
    em, tg = channels()
    out = []
    if em:
        out.append(("Email",) + notify.send_email(em, subject, text))
    if tg:
        out.append(("Telegram",) + notify.send_telegram(tg, text))
    return out


def auto_send(ctx, rows):
    """Envoi automatique si activé (appelé après une saisie ou un import). Retourne un court message."""
    if not st.session_state.get("auto_notify") or rows.empty:
        return ""
    res = send_all(ctx, ctx.T("alert_subject", app=ctx.app_name), alert_text(ctx, rows))
    if not res:
        return ""
    return ctx.T("alert_sent", ch=", ".join(c for c, ok, _ in res if ok) or "—")


def _flash(kind, text):
    st.session_state.setdefault("notif_msgs", []).append((kind, text))


def _settings_ui(ctx, em, tg):
    """Formulaires de configuration Gmail / Telegram (enregistrés dans settings.json)."""
    T = ctx.T
    em0, tg0 = em or {}, tg or {}
    with st.expander(T("notif_setup"), expanded=not (em or tg)):
        t1, t2 = st.tabs(["📧 Gmail / SMTP", "✈️ Telegram"])
        with t1:
            st.markdown(T("gmail_help"))
            with st.form("email_form"):
                user = st.text_input(T("em_user"), value=em0.get("user", DEFAULT_GMAIL), placeholder="exemple@gmail.com")
                pwd = st.text_input(T("em_pwd"), value="", type="password",
                                    placeholder="•••• •••• •••• ••••" if em0.get("password") else "abcd efgh ijkl mnop")
                to = st.text_input(T("em_to"), value=em0.get("to", DEFAULT_GMAIL))
                with st.expander(T("advanced")):
                    host = st.text_input("SMTP", value=str(em0.get("host", "smtp.gmail.com")))
                    port = st.number_input("Port", 1, 65535, int(em0.get("port", 587)))
                c1, c2 = st.columns(2)
                save = c1.form_submit_button(T("save_cfg"))
                test = c2.form_submit_button(T("save_test"), type="primary")
            if save or test:
                pwd_final = pwd or em0.get("password", "")
                cfg = {"host": host.strip(), "port": int(port), "user": user.strip(),
                       "password": pwd_final, "to": (to or user).strip()}
                if not (cfg["user"] and cfg["password"]):
                    st.error(T("cfg_missing"))
                else:
                    ok, msg = notify.save_settings(email=cfg)
                    _flash("success" if ok else "error", T("cfg_saved") if ok else msg)
                    if test:
                        ok2, msg2 = notify.send_email(cfg, f"{ctx.app_name} — test", T("alert_test", app=ctx.app_name))
                        _flash("success" if ok2 else "error", f"Email : {'OK → ' + msg2 if ok2 else msg2}")
                    st.rerun()
        with t2:
            st.markdown(T("tg_help"))
            token = st.text_input("Token (@BotFather)", value=tg0.get("token", ""), type="password", key="tg_token")
            chat = st.text_input("chat_id", value=str(tg0.get("chat_id", "")), key="tg_chat")
            c1, c2, c3 = st.columns(3)
            if c1.button(T("tg_find"), disabled=not token):
                cid, info = notify.find_telegram_chat_id(token)
                if cid:
                    st.session_state["tg_chat"] = cid
                    st.success(f"chat_id = {cid} ({info})")
                    st.rerun()
                else:
                    st.error(info)
            if c2.button(T("save_cfg"), key="tg_save", disabled=not (token and chat)):
                ok, msg = notify.save_settings(telegram={"token": token.strip(), "chat_id": chat.strip()})
                _flash("success" if ok else "error", T("cfg_saved") if ok else msg)
                st.rerun()
            if c3.button(T("save_test"), key="tg_test", type="primary", disabled=not (token and chat)):
                cfg = {"token": token.strip(), "chat_id": chat.strip()}
                ok, msg = notify.save_settings(telegram=cfg)
                ok2, msg2 = notify.send_telegram(cfg, T("alert_test", app=ctx.app_name))
                _flash("success" if ok2 else "error", f"Telegram : {'OK' if ok2 else msg2}")
                st.rerun()


def render_notif(ctx):
    T = ctx.T
    ctx.section(T("notif_title"), "iot")
    for kind, text in st.session_state.pop("notif_msgs", []):
        getattr(st, kind)(text)
    em, tg = channels()
    c1, c2 = st.columns(2)
    (c1.success if em else c1.warning)(f"Email : {T('configured') if em else T('not_configured')}")
    (c2.success if tg else c2.warning)(f"Telegram : {T('configured') if tg else T('not_configured')}")
    _settings_ui(ctx, em, tg)
    st.checkbox(T("auto_notify"), key="auto_notify", disabled=not (em or tg))
    b1, b2 = st.columns(2)
    res = []
    if b1.button(T("send_test"), disabled=not (em or tg)):
        res = send_all(ctx, f"{ctx.app_name} — test", T("alert_test", app=ctx.app_name))
    crit = ctx.at_risk[ctx.at_risk.risk >= ctx.CRIT]
    if b2.button(T("send_now", n=len(crit)), disabled=not (em or tg) or crit.empty):
        res = send_all(ctx, T("alert_subject", app=ctx.app_name), alert_text(ctx, crit))
    for ch, ok, msg in res:
        (st.success if ok else st.error)(f"{ch} : {'OK' if ok else msg}")
    if crit.empty:
        st.info(T("no_critical"))
    else:
        with st.expander(T("preview_msg")):
            st.text(alert_text(ctx, crit))


# ═════════════════════ 17. CARTE DE L'USINE ═════════════════════
ATELIERS = [("L", "A"), ("M", "B"), ("H", "C")]
GRID_COLS, GRID_ROWS = 8, 6


def factory_fig(ctx, data, only=None):
    """Plan schématique : un atelier par qualité (L/M/H), machines en marche colorées selon le risque."""
    T = ctx.T
    per = GRID_COLS * GRID_ROWS
    fig = go.Figure()
    levels = [("crit", ctx.RED), ("high", ctx.COPPER), ("watch", ctx.AMBER), ("ok", ctx.TEAL)]
    pts = {k: ([], [], []) for k, _ in levels}
    run = data[data.failure == 0]
    shown = [(q, n) for q, n in ATELIERS if only in (None, q)]
    for i, (q, name) in enumerate(shown):
        x0 = i * (GRID_COLS + 2)
        n_fail = int(((data.type == q) & (data.failure == 1)).sum())
        top = run[run.type == q].nlargest(per, "risk")
        n_crit = int((top.risk >= ctx.CRIT).sum())
        fig.add_shape(type="rect", x0=x0 - .7, x1=x0 + GRID_COLS - .3, y0=-GRID_ROWS + .3, y1=.8,
                      line=dict(color="#6d8a99", width=2), fillcolor="rgba(109,138,153,.12)", layer="below")
        fig.add_annotation(x=x0 + (GRID_COLS - 1) / 2, y=1.35, showarrow=False, font=dict(size=14),
                           text=f"<b>{T('atelier')} {name}</b> · {T('quality')} {q}<br>"
                                f"<span style='font-size:11px'>{n_crit} {T('lvl_crit').lower()} · {n_fail} {T('failures').lower()}</span>")
        for j, r in enumerate(top.itertuples()):
            lk = level_key(ctx, r.risk)
            xs, ys, tx = pts[lk]
            xs.append(x0 + j % GRID_COLS)
            ys.append(-(j // GRID_COLS))
            tx.append(f"<b>{r.product_id}</b><br>{T('score')} : {int(r.risk)}%<br>{T('cause_' + r.risk_cause)}")
    for k, color in levels:
        xs, ys, tx = pts[k]
        if xs:
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="markers", name=T("lvl_" + k), text=tx, hoverinfo="text",
                                     marker=dict(size=24, color=color, line=dict(width=2, color="rgba(255,255,255,.7)"),
                                                 symbol="square")))
    fig.update_xaxes(visible=False, range=[-1.2, len(shown) * (GRID_COLS + 2) - 1.5])
    fig.update_yaxes(visible=False, range=[-GRID_ROWS - .2, 2.4], scaleanchor="x")
    fig.update_layout(title=T("map_chart"), legend=dict(orientation="h", y=-.02))
    return fig


def render_map(ctx):
    T = ctx.T
    ctx.section(T("map_title"), "machines")
    st.caption(T("map_help", n=GRID_COLS * GRID_ROWS))
    sel = st.radio(T("atelier"), ["*"] + [q for q, _ in ATELIERS], horizontal=True,
                   format_func=lambda q: T("all") if q == "*" else f"{T('atelier')} {dict(ATELIERS)[q]} ({q})")
    ctx.show(factory_fig(ctx, ctx.data, None if sel == "*" else sel), 520)


# ═════════════════════ 14. MODE ÉCRAN ATELIER ═════════════════════
WORKSHOP_CSS = """
<style>
[data-testid="stSidebar"], [data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"],
[data-testid="stHeader"] {display:none !important;}
.block-container {padding-top:.8rem !important; max-width:100% !important;}
.ws-top {display:flex; align-items:center; gap:18px; margin-bottom:10px;}
.ws-top img {width:64px; height:64px;} .ws-top h1 {margin:0; padding:0; font-size:2rem; line-height:1.1;}
.ws-clock {margin-left:auto; font-size:2.4rem; font-weight:700; font-family:'Bricolage Grotesque',sans-serif;}
.ws-big {display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:8px 0 14px;}
.ws-big div {border-radius:14px; padding:14px 20px; background:#fff; border:1px solid #dde5e9; border-bottom:5px solid var(--c);}
.ws-big small {display:block; font-size:1.05rem; color:#5b6f7a;}
.ws-big b {font-size:3.4rem; line-height:1.1; font-family:'Bricolage Grotesque',sans-serif; color:var(--c);}
.ws-list {display:grid; grid-template-columns:repeat(2,1fr); gap:10px;}
.ws-card {border-radius:12px; padding:12px 18px; background:#fff; border:1px solid #dde5e9; border-left:8px solid var(--c);}
.ws-card b {font-size:1.6rem;} .ws-card span {float:right; font-size:1.8rem; font-weight:800; color:var(--c);}
.ws-card div {font-size:1.05rem; color:#5b6f7a;}
</style>
"""


@st.fragment(run_every=30)
def _workshop_body(ctx):
    T = ctx.T
    raw = ctx.load_raw()                       # relit le disque : les nouvelles saisies apparaissent seules
    data = ctx.add_risk(ctx.enrich(raw))
    ar = data[(data.failure == 0) & (data.risk >= ctx.WATCH)].sort_values("risk", ascending=False)
    n_crit = int((ar.risk >= ctx.CRIT).sum())
    n_high = int(((ar.risk >= ctx.HIGH) & (ar.risk < ctx.CRIT)).sum())
    big = [(T("machines"), f"{len(data):,}".replace(",", " "), ctx.BLUE), (T("failures"), int(data.failure.sum()), ctx.RED),
           (T("lvl_crit"), n_crit, ctx.RED), (T("lvl_high"), n_high, ctx.COPPER)]
    st.markdown("<div class='ws-big'>" + "".join(f"<div style='--c:{c}'><small>{l}</small><b>{v}</b></div>"
                                                 for l, v, c in big) + "</div>", unsafe_allow_html=True)
    left, right = st.columns([1, 1.25])
    with left:
        st.markdown(f"### {T('ws_top')}")
        if ar.empty:
            st.success(T("no_critical"))
        cards = "".join(
            f"<div class='ws-card' style='--c:{ctx.zone_color(r.risk)}'><span>{int(r.risk)}%</span><b>{r.product_id}</b>"
            f"<div>{T('cause_' + r.risk_cause)} — {T('action_' + r.risk_cause)}</div></div>"
            for r in ar.head(8).itertuples())
        st.markdown(f"<div class='ws-list' style='grid-template-columns:1fr'>{cards}</div>", unsafe_allow_html=True)
    with right:
        ctx.show(factory_fig(ctx, data), 520)
    st.caption(f"{T('ws_updated')} {now():%H:%M:%S} · {T('ws_auto')}")


def render_workshop(ctx):
    T = ctx.T
    st.markdown(WORKSHOP_CSS, unsafe_allow_html=True)
    a, b = st.columns([6, 1])
    a.markdown(f"<div class='ws-top'><img src='{ctx.logo_uri}'/><h1>{ctx.app_name}</h1>"
               f"<div class='ws-clock'>{now():%H:%M}</div></div>", unsafe_allow_html=True)
    if b.button(T("exit_workshop")):
        st.session_state.workshop = False
        st.rerun()
    _workshop_body(ctx)


def log_measurement(pid, rpm, tq, wear, air, proc, risk):
    """Ajoute une mesure à l'historique d'une machine (history.csv)."""
    hist = get_hist()
    new = pd.DataFrame([{"machine": pid, "ts": now().strftime("%Y-%m-%d %H:%M:%S"), "rpm": rpm, "torque": tq,
                         "wear": wear, "air": air, "proc": proc, "risk": risk}]).astype(str)
    st.session_state.hist = pd.concat([hist, new], ignore_index=True)
    _write_csv(st.session_state.hist, HIST_CSV)
