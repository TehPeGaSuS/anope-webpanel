from flask import Blueprint, render_template, request, flash, redirect, url_for, g
from rpc import rpc, AnopeError
from auth import login_required
from utils import (parse_akill_view, parse_xline_view, parse_os_userlist, parse_os_chanlist,
                   parse_os_oper_list, parse_os_ignore_list, parse_os_news_list,
                   parse_os_forbid_list, parse_os_session_list, parse_os_exception_list,
                   as_search_mask, as_userlist_mask)

bp = Blueprint("operserv", __name__, url_prefix="/operserv")


def oper_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        # opertype presence means they're an oper
        try:
            account = rpc("anope.account", g.account)
            if not account.get("opertype"):
                flash("Access denied.", "error")
                return redirect(url_for("dashboard"))
        except AnopeError as e:
            flash(e.message, "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return wrapper


@bp.route("/")
@bp.route("/akill")
@login_required
@oper_required
def akill():
    try:
        result = rpc("anope.command", g.account, "OperServ", "AKILL VIEW")
        entries = parse_akill_view(result)
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    return render_template("operserv/akill.html", entries=entries)


@bp.route("/akill/add", methods=["POST"])
@login_required
@oper_required
def akill_add():
    mask = request.form.get("mask", "").strip()
    expiry = request.form.get("expiry", "0").strip()
    reason = request.form.get("reason", "").strip()
    if not mask or not reason:
        flash("Mask and reason are required.", "error")
        return redirect(url_for("operserv.akill"))
    try:
        rpc("anope.command", g.account, "OperServ", f"AKILL ADD +{expiry} {mask} {reason}")
        flash(f"AKILL added for {mask}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("operserv.akill"))


@bp.route("/akill/del", methods=["POST"])
@login_required
@oper_required
def akill_del():
    mask = request.form.get("mask", "").strip()
    try:
        rpc("anope.command", g.account, "OperServ", f"AKILL DEL {mask}")
        flash(f"AKILL removed for {mask}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("operserv.akill"))


# ── Sessions / session-limit exceptions ─────────────────────────────────────
# SESSION LIST requires a threshold strictly greater than 1 (Anope rejects
# 1 as "Invalid threshold value") — default to 2 so the page loads with data
# out of the box instead of the raw error text as if it were a session.

@bp.route("/sessions")
@login_required
@oper_required
def sessions():
    threshold = request.args.get("threshold", "2").strip() or "2"
    try:
        result = rpc("anope.command", g.account, "OperServ", f"SESSION LIST {threshold}")
        sessions_ = parse_os_session_list(result)
    except AnopeError as e:
        flash(e.message, "error")
        sessions_ = []
    try:
        exc_result = rpc("anope.command", g.account, "OperServ", "EXCEPTION LIST")
        exceptions = parse_os_exception_list(exc_result)
    except AnopeError as e:
        flash(e.message, "error")
        exceptions = []
    return render_template(
        "operserv/sessions.html", sessions=sessions_, exceptions=exceptions, threshold=threshold,
    )


@bp.route("/sessions/exception/add", methods=["POST"])
@login_required
@oper_required
def exception_add():
    mask = request.form.get("mask", "").strip()
    limit = request.form.get("limit", "").strip()
    expiry = request.form.get("expiry", "").strip()
    reason = request.form.get("reason", "").strip()
    if not mask or not limit or not reason:
        flash("Mask, limit and reason are required.", "error")
        return redirect(url_for("operserv.sessions"))
    cmd = "EXCEPTION ADD"
    if expiry:
        cmd += f" +{expiry}"
    cmd += f" {mask} {limit} {reason}"
    try:
        rpc("anope.command", g.account, "OperServ", cmd)
        flash(f"Session exception added for {mask}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("operserv.sessions"))


@bp.route("/sessions/exception/del", methods=["POST"])
@login_required
@oper_required
def exception_del():
    mask = request.form.get("mask", "").strip()
    try:
        rpc("anope.command", g.account, "OperServ", f"EXCEPTION DEL {mask}")
        flash(f"Session exception removed for {mask}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("operserv.sessions"))


# ── News ─────────────────────────────────────────────────────────────────────
# NOTE: there is no generic "NEWS" command in Anope — it's three separate
# commands (LOGONNEWS/OPERNEWS/RANDOMNEWS), each with its own LIST subcommand.
# The previous version of this route called "NEWS LIST", which doesn't exist
# and always returned "No such command" — confirmed live against a running
# Anope instance.

@bp.route("/news")
@login_required
@oper_required
def news():
    sections = []
    for label, cmd in (("Logon News", "LOGONNEWS"), ("Oper News", "OPERNEWS"), ("Random News", "RANDOMNEWS")):
        try:
            result = rpc("anope.command", g.account, "OperServ", f"{cmd} LIST")
            entries = parse_os_news_list(result)
        except AnopeError as e:
            flash(e.message, "error")
            entries = []
        sections.append({"label": label, "cmd": cmd, "entries": entries})
    return render_template("operserv/news.html", sections=sections)


@bp.route("/news/add", methods=["POST"])
@login_required
@oper_required
def news_add():
    cmd = request.form.get("cmd", "").strip().upper()
    text = request.form.get("text", "").strip()
    if cmd not in ("LOGONNEWS", "OPERNEWS", "RANDOMNEWS") or not text:
        flash("Invalid news entry.", "error")
        return redirect(url_for("operserv.news"))
    try:
        rpc("anope.command", g.account, "OperServ", f"{cmd} ADD {text}")
        flash("News entry added.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("operserv.news"))


@bp.route("/news/del", methods=["POST"])
@login_required
@oper_required
def news_del():
    cmd = request.form.get("cmd", "").strip().upper()
    num = request.form.get("num", "").strip()
    if cmd not in ("LOGONNEWS", "OPERNEWS", "RANDOMNEWS") or not num:
        flash("Invalid news entry.", "error")
        return redirect(url_for("operserv.news"))
    try:
        rpc("anope.command", g.account, "OperServ", f"{cmd} DEL {num}")
        flash("News entry removed.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("operserv.news"))


# ── Stats ────────────────────────────────────────────────────────────────────

@bp.route("/stats")
@login_required
@oper_required
def stats():
    mode = request.args.get("mode", "").strip().upper()
    valid = {"", "AKILL", "HASH", "PASSWORD", "UPLINK", "UPTIME", "ALL"}
    if mode not in valid:
        mode = ""
    cmd = f"STATS {mode}".strip()
    try:
        result = rpc("anope.command", g.account, "OperServ", cmd)
    except AnopeError as e:
        flash(e.message, "error")
        result = []
    return render_template("operserv/stats.html", result=result, mode=mode)


@bp.route("/seen", methods=["GET", "POST"])
@login_required
@oper_required
def seen():
    result = None
    if request.method == "POST":
        clear_time = request.form.get("clear_time", "").strip()
        try:
            result = rpc("anope.command", g.account, "OperServ", f"SEEN CLEAR {clear_time}")
        except AnopeError as e:
            flash(e.message, "error")
        return redirect(url_for("operserv.seen"))
    try:
        result = rpc("anope.command", g.account, "OperServ", "SEEN STATS")
    except AnopeError as e:
        flash(e.message, "error")
        result = []
    return render_template("operserv/seen.html", result=result)


# ── User / channel list ─────────────────────────────────────────────────────

@bp.route("/userlist")
@login_required
@oper_required
def userlist():
    pattern = request.args.get("pattern", "").strip()
    page = max(1, int(request.args.get("page", 1)))
    mask = as_userlist_mask(pattern)
    cmd = f"USERLIST {mask}" if mask else "USERLIST"
    try:
        result = rpc("anope.command", g.account, "OperServ", cmd)
        entries = parse_os_userlist(result)
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    per_page = 100
    total = len(entries)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    start = (page - 1) * per_page
    entries_page = entries[start:start + per_page]
    return render_template("operserv/userlist.html", entries=entries_page, pattern=pattern,
                           page=page, total_pages=total_pages, total=total)


@bp.route("/chanlist")
@login_required
@oper_required
def chanlist():
    pattern = request.args.get("pattern", "").strip()
    mask = as_search_mask(pattern)
    cmd = f"CHANLIST {mask}" if mask else "CHANLIST"
    try:
        result = rpc("anope.command", g.account, "OperServ", cmd)
        entries = parse_os_chanlist(result)
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    return render_template("operserv/chanlist.html", entries=entries, pattern=pattern)


# ── Forbid ───────────────────────────────────────────────────────────────────

FORBID_TYPES = ("NICK", "CHAN", "EMAIL", "PASSWORD", "REGISTER")


@bp.route("/forbid")
@login_required
@oper_required
def forbid():
    ftype = request.args.get("type", "NICK").upper()
    if ftype not in FORBID_TYPES:
        ftype = "NICK"
    search = request.args.get("search", "").strip()
    page = max(1, int(request.args.get("page", 1)))
    try:
        result = rpc("anope.command", g.account, "OperServ", f"FORBID LIST {ftype}")
        entries = parse_os_forbid_list(result)
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    # FORBID LIST takes no mask/search argument (unlike USERLIST/CHANLIST),
    # so filtering happens here against what Anope already returned.
    if search:
        needle = search.lower()
        entries = [e for e in entries
                   if needle in e["mask"].lower() or needle in e["creator"].lower()
                   or needle in e["reason"].lower()]
    per_page = 100
    total = len(entries)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    start = (page - 1) * per_page
    entries_page = entries[start:start + per_page]
    return render_template("operserv/forbid.html", entries=entries_page, ftype=ftype, search=search,
                           types=FORBID_TYPES, page=page, total_pages=total_pages, total=total)


@bp.route("/forbid/add", methods=["POST"])
@login_required
@oper_required
def forbid_add():
    ftype = request.form.get("type", "").upper()
    entry = request.form.get("entry", "").strip()
    expiry = request.form.get("expiry", "").strip()
    reason = request.form.get("reason", "").strip()
    if ftype not in FORBID_TYPES or not entry or not reason:
        flash("Type, entry, and reason are required.", "error")
        return redirect(url_for("operserv.forbid", type=ftype))
    prefix = f"+{expiry} " if expiry else ""
    try:
        result = rpc("anope.command", g.account, "OperServ", f"FORBID ADD {ftype} {prefix}{entry} {reason}")
        flash(result[0] if result else "Forbid added.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("operserv.forbid", type=ftype))


@bp.route("/forbid/del", methods=["POST"])
@login_required
@oper_required
def forbid_del():
    ftype = request.form.get("type", "").upper()
    entry = request.form.get("entry", "").strip()
    try:
        rpc("anope.command", g.account, "OperServ", f"FORBID DEL {ftype} {entry}")
        flash(f"{entry} un-forbidden.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("operserv.forbid", type=ftype))


# ── Services operators ──────────────────────────────────────────────────────

@bp.route("/oper")
@login_required
@oper_required
def oper_list():
    try:
        result = rpc("anope.command", g.account, "OperServ", "OPER LIST")
        entries = parse_os_oper_list(result)
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    try:
        info = rpc("anope.command", g.account, "OperServ", "OPER INFO")
        types = [line.strip() for line in info[1:] if line.strip()]
    except AnopeError:
        types = []
    return render_template("operserv/oper.html", entries=entries, types=types)


@bp.route("/oper/add", methods=["POST"])
@login_required
@oper_required
def oper_add():
    name = request.form.get("name", "").strip()
    optype = request.form.get("type", "").strip()
    if not name or not optype:
        flash("Nick and opertype are required.", "error")
        return redirect(url_for("operserv.oper_list"))
    try:
        rpc("anope.command", g.account, "OperServ", f"OPER ADD {name} {optype}")
        flash(f"{name} added as {optype}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("operserv.oper_list"))


@bp.route("/oper/del", methods=["POST"])
@login_required
@oper_required
def oper_del():
    name = request.form.get("name", "").strip()
    try:
        rpc("anope.command", g.account, "OperServ", f"OPER DEL {name}")
        flash(f"Oper privileges removed from {name}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("operserv.oper_list"))


# ── Services ignore list ────────────────────────────────────────────────────

@bp.route("/ignore")
@login_required
@oper_required
def ignore():
    try:
        result = rpc("anope.command", g.account, "OperServ", "IGNORE LIST")
        entries = parse_os_ignore_list(result)
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    return render_template("operserv/ignore.html", entries=entries)


@bp.route("/ignore/add", methods=["POST"])
@login_required
@oper_required
def ignore_add():
    mask = request.form.get("mask", "").strip()
    expiry = request.form.get("expiry", "0").strip() or "0"
    reason = request.form.get("reason", "").strip()
    if not mask:
        flash("Nick or mask is required.", "error")
        return redirect(url_for("operserv.ignore"))
    try:
        rpc("anope.command", g.account, "OperServ", f"IGNORE ADD {expiry} {mask} {reason}".rstrip())
        flash(f"{mask} added to ignore list.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("operserv.ignore"))


@bp.route("/ignore/del", methods=["POST"])
@login_required
@oper_required
def ignore_del():
    mask = request.form.get("mask", "").strip()
    try:
        rpc("anope.command", g.account, "OperServ", f"IGNORE DEL {mask}")
        flash(f"{mask} removed from ignore list.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("operserv.ignore"))


# ── Chankill ─────────────────────────────────────────────────────────────────

@bp.route("/chankill", methods=["GET", "POST"])
@login_required
@oper_required
def chankill():
    if request.method == "POST":
        channel = request.form.get("channel", "").strip()
        expiry = request.form.get("expiry", "").strip()
        reason = request.form.get("reason", "").strip()
        if not channel or not reason:
            flash("Channel and reason are required.", "error")
            return redirect(url_for("operserv.chankill"))
        if not channel.startswith("#"):
            channel = "#" + channel
        prefix = f"+{expiry} " if expiry else ""
        try:
            result = rpc("anope.command", g.account, "OperServ", f"CHANKILL {prefix}{channel} {reason}")
            flash(" ".join(result) if result else f"CHANKILL issued for {channel}.", "success")
        except AnopeError as e:
            flash(e.message, "error")
        return redirect(url_for("operserv.chankill"))
    return render_template("operserv/chankill.html")


# ── Jupe ─────────────────────────────────────────────────────────────────────

@bp.route("/jupe", methods=["GET", "POST"])
@login_required
@oper_required
def jupe():
    if request.method == "POST":
        server = request.form.get("server", "").strip()
        reason = request.form.get("reason", "").strip()
        if not server:
            flash("Server name is required.", "error")
            return redirect(url_for("operserv.jupe"))
        try:
            result = rpc("anope.command", g.account, "OperServ", f"JUPE {server} {reason}".rstrip())
            flash(" ".join(result) if result else f"{server} juped.", "success")
        except AnopeError as e:
            flash(e.message, "error")
        return redirect(url_for("operserv.jupe"))
    return render_template("operserv/jupe.html")


# ── Mode / Umode ─────────────────────────────────────────────────────────────

@bp.route("/mode", methods=["GET", "POST"])
@login_required
@oper_required
def mode():
    if request.method == "POST":
        kind = request.form.get("kind", "channel")
        target = request.form.get("target", "").strip()
        modes = request.form.get("modes", "").strip()
        if not target or not modes:
            flash("Target and modes are required.", "error")
            return redirect(url_for("operserv.mode"))
        cmd = "MODE" if kind == "channel" else "UMODE"
        try:
            result = rpc("anope.command", g.account, "OperServ", f"{cmd} {target} {modes}")
            flash(" ".join(result) if result else f"Modes updated for {target}.", "success")
        except AnopeError as e:
            flash(e.message, "error")
        return redirect(url_for("operserv.mode"))
    return render_template("operserv/mode.html")


# ── Noop ─────────────────────────────────────────────────────────────────────

@bp.route("/noop", methods=["GET", "POST"])
@login_required
@oper_required
def noop():
    if request.method == "POST":
        action = request.form.get("action", "").strip().upper()
        server = request.form.get("server", "").strip()
        if action not in ("SET", "REVOKE") or not server:
            flash("Server and action are required.", "error")
            return redirect(url_for("operserv.noop"))
        try:
            result = rpc("anope.command", g.account, "OperServ", f"NOOP {action} {server}")
            flash(" ".join(result) if result else f"NOOP {action} issued for {server}.", "success")
        except AnopeError as e:
            flash(e.message, "error")
        return redirect(url_for("operserv.noop"))
    return render_template("operserv/noop.html")


# ── Danger zone ──────────────────────────────────────────────────────────────
# RELOAD/UPDATE don't stop the service. QUIT/SHUTDOWN/RESTART do, and Anope
# itself requires the exact configured network name as confirmation
# (modules/operserv/os_shutdown.cpp: NetworkNameGiven() does a case-sensitive
# compare against networkinfo.networkname) — the form surfaces that same value
# so the admin types it deliberately rather than a generated code.

@bp.route("/danger")
@login_required
@oper_required
def danger():
    return render_template("operserv/danger.html")


@bp.route("/danger/reload", methods=["POST"])
@login_required
@oper_required
def danger_reload():
    try:
        result = rpc("anope.command", g.account, "OperServ", "RELOAD")
        flash(" ".join(result) if result else "Configuration reloaded.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("operserv.danger"))


@bp.route("/danger/update", methods=["POST"])
@login_required
@oper_required
def danger_update():
    try:
        result = rpc("anope.command", g.account, "OperServ", "UPDATE")
        flash(" ".join(result) if result else "Databases updated.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("operserv.danger"))


@bp.route("/danger/<action>", methods=["POST"])
@login_required
@oper_required
def danger_action(action):
    action = action.upper()
    if action not in ("QUIT", "SHUTDOWN", "RESTART"):
        flash("Unknown action.", "error")
        return redirect(url_for("operserv.danger"))
    import os
    confirm = request.form.get("confirm", "").strip()
    network_name = os.environ.get("NETWORK_NAME", "")
    if confirm != network_name:
        flash("Network name did not match. Action cancelled.", "error")
        return redirect(url_for("operserv.danger"))
    try:
        rpc("anope.command", g.account, "OperServ", f"{action} {confirm}")
        flash(f"{action} issued.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("operserv.danger"))


# ── SNLINE / SQLINE ──────────────────────────────────────────────────────────
# Both share AKILL's underlying XLine machinery and reply shape (see
# parse_xline_view). SNLINE ADD has a real Anope-side quirk: its multi-word
# reason is only captured correctly when an explicit +expiry is also given
# (confirmed live) — the panel always sends one, defaulting to 30d, so the
# reason field behaves the same as AKILL/SQLINE's from the user's perspective.

@bp.route("/snline")
@login_required
@oper_required
def snline():
    try:
        result = rpc("anope.command", g.account, "OperServ", "SNLINE VIEW")
        entries = parse_xline_view(result)
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    return render_template("operserv/snline.html", entries=entries)


@bp.route("/snline/add", methods=["POST"])
@login_required
@oper_required
def snline_add():
    mask = request.form.get("mask", "").strip()
    expiry = request.form.get("expiry", "").strip() or "30d"
    reason = request.form.get("reason", "").strip()
    if not mask or not reason:
        flash("Mask and reason are required.", "error")
        return redirect(url_for("operserv.snline"))
    try:
        rpc("anope.command", g.account, "OperServ", f"SNLINE ADD +{expiry} {mask}:{reason}")
        flash(f"SNLINE added for {mask}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("operserv.snline"))


@bp.route("/snline/del", methods=["POST"])
@login_required
@oper_required
def snline_del():
    # Deleting by mask text breaks for any mask containing a space (Anope
    # tokenizes the raw command on spaces before matching, same root cause
    # as the ADD reason-truncation bug above) — SNLINE masks are realname
    # masks, which legitimately can and do contain spaces. Delete by
    # Anope's own stable per-entry ID instead (SetSyntax explicitly lists
    # "id" as a valid DEL key), which is always a single space-free token.
    target = request.form.get("target", "").strip()
    try:
        rpc("anope.command", g.account, "OperServ", f"SNLINE DEL {target}")
        flash("SNLINE removed.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("operserv.snline"))


@bp.route("/sqline")
@login_required
@oper_required
def sqline():
    try:
        result = rpc("anope.command", g.account, "OperServ", "SQLINE VIEW")
        entries = parse_xline_view(result)
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    return render_template("operserv/sqline.html", entries=entries)


@bp.route("/sqline/add", methods=["POST"])
@login_required
@oper_required
def sqline_add():
    mask = request.form.get("mask", "").strip()
    expiry = request.form.get("expiry", "").strip()
    reason = request.form.get("reason", "").strip()
    if not mask or not reason:
        flash("Mask and reason are required.", "error")
        return redirect(url_for("operserv.sqline"))
    cmd = "SQLINE ADD"
    if expiry:
        cmd += f" +{expiry}"
    cmd += f" {mask} {reason}"
    try:
        rpc("anope.command", g.account, "OperServ", cmd)
        flash(f"SQLINE added for {mask}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("operserv.sqline"))


@bp.route("/sqline/del", methods=["POST"])
@login_required
@oper_required
def sqline_del():
    # Delete by ID, same reasoning as snline_del — SQLINE masks (nick/
    # channel masks) can't contain spaces in practice, but ID is just as
    # reliable and keeps both pages consistent.
    target = request.form.get("target", "").strip()
    try:
        rpc("anope.command", g.account, "OperServ", f"SQLINE DEL {target}")
        flash("SQLINE removed.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("operserv.sqline"))


# ── DEFCON ───────────────────────────────────────────────────────────────────
# There is no read-only "current level" query in Anope — DEFCON is a
# set-only command (confirmed live: bare "DEFCON" with no level argument
# returns "No such command", not a status reply). The page mirrors that:
# it's a set of action buttons with no persistent "current status" display,
# same as an oper would experience issuing this from IRC directly. Level 5
# (normal operation / undo) needs no confirmation; levels 1-4 require typing
# the network name, same friction as the Danger Zone's restart/shutdown/quit.

@bp.route("/defcon")
@login_required
@oper_required
def defcon():
    return render_template("operserv/defcon.html")


@bp.route("/defcon/<int:level>", methods=["POST"])
@login_required
@oper_required
def defcon_set(level):
    import os
    if level not in (1, 2, 3, 4, 5):
        flash("Invalid DEFCON level.", "error")
        return redirect(url_for("operserv.defcon"))
    if level != 5:
        confirm = request.form.get("confirm", "").strip()
        network_name = os.environ.get("NETWORK_NAME", "")
        if confirm != network_name:
            flash("Network name did not match. Action cancelled.", "error")
            return redirect(url_for("operserv.defcon"))
    try:
        result = rpc("anope.command", g.account, "OperServ", f"DEFCON {level}")
        flash(" ".join(result) if result else f"DEFCON level set to {level}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("operserv.defcon"))


# ── KILL ─────────────────────────────────────────────────────────────────────
# One-shot action, not a persistent list — same "form posts to itself" shape
# as Force Mode. KILL is an inversion of the usual "failures look like
# success" gotcha: confirmed live against os_kill.cpp — on a REAL kill it
# sends no reply at all (empty result), and only replies with text on
# failure ("Nick X isn't currently in use." / "Access denied."). So here a
# non-empty result means failure, the opposite of every other command.

@bp.route("/kill", methods=["GET", "POST"])
@login_required
@oper_required
def kill():
    if request.method == "POST":
        target = request.form.get("target", "").strip()
        reason = request.form.get("reason", "").strip()
        if not target:
            flash("Target nick is required.", "error")
            return redirect(url_for("operserv.kill"))
        cmd = f"KILL {target}"
        if reason:
            cmd += f" {reason}"
        try:
            result = rpc("anope.command", g.account, "OperServ", cmd)
            if result:
                flash(" ".join(result), "error")
            else:
                flash(f"{target} killed.", "success")
        except AnopeError as e:
            flash(e.message, "error")
        return redirect(url_for("operserv.kill"))
    return render_template("operserv/kill.html")
