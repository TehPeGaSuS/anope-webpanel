from flask import Blueprint, render_template, request, flash, redirect, url_for, g
from rpc import rpc, AnopeError
from auth import login_required
from utils import parse_cert_list

bp = Blueprint("nickserv", __name__, url_prefix="/nickserv")


@bp.route("/")
@bp.route("/info")
@login_required
def info():
    try:
        account = rpc("anope.account", g.account)
    except AnopeError as e:
        flash(e.message, "error")
        account = None
    return render_template("nickserv/info.html", account=account)


@bp.route("/cert")
@login_required
def cert():
    try:
        result = rpc("anope.command", g.account, "NickServ", "CERT LIST")
        certs = parse_cert_list(result)
    except AnopeError as e:
        flash(e.message, "error")
        certs = []
    return render_template("nickserv/cert.html", certs=certs)


@bp.route("/cert/add", methods=["POST"])
@login_required
def cert_add():
    fingerprint = request.form.get("fingerprint", "").strip()
    if not fingerprint:
        flash("Fingerprint is required.", "error")
        return redirect(url_for("nickserv.cert"))
    try:
        rpc("anope.command", g.account, "NickServ", f"CERT ADD {fingerprint}")
        flash("Certificate added.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("nickserv.cert"))


@bp.route("/cert/del", methods=["POST"])
@login_required
def cert_del():
    fingerprint = request.form.get("fingerprint", "").strip()
    if not fingerprint:
        flash("Fingerprint is required.", "error")
        return redirect(url_for("nickserv.cert"))
    try:
        rpc("anope.command", g.account, "NickServ", f"CERT DEL {fingerprint}")
        flash("Certificate removed.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("nickserv.cert"))


@bp.route("/alist")
@login_required
def alist():
    try:
        account = rpc("anope.account", g.account)
    except AnopeError as e:
        flash(e.message, "error")
        account = None
    return render_template("nickserv/alist.html", account=account)


def _anope_confirmed(result, marker):
    """
    Anope's RPC layer reports command-level failures (wrong code, expired
    request, etc.) as an ordinary successful "result" reply — NOT a JSON-RPC
    "error" — so rpc.py's AnopeError never fires on them. A caller that acts
    on "no exception was raised" alone will treat a wrong/garbage code as a
    success. Only treat it as success if `marker` (a substring unique to the
    real Anope success reply) is actually present; fail closed otherwise.
    """
    return any(marker.lower() in line.lower() for line in (result or []))


@bp.route("/confirm", methods=["GET", "POST"])
@login_required
def confirm():
    # Manual code entry while logged in — for a pending EMAIL CHANGE confirmation.
    # (Registration confirmation can't happen here: an unconfirmed account can't
    # log into the panel in the first place, so that flow is link-only — see
    # confirm_register() below.)
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        try:
            result = rpc("anope.command", g.account, "NickServ", f"CONFIRM EMAIL {code}")
            if _anope_confirmed(result, "has been changed from"):
                flash("Email confirmed successfully.", "success")
                return redirect(url_for("nickserv.info"))
            flash(result[0] if result else "Email confirmation failed.", "error")
        except AnopeError as e:
            flash(e.message, "error")
    return render_template("nickserv/confirm.html")


@bp.route("/confirm/register/<nick>/<code>")
def confirm_register(nick, code):
    # Unauthenticated — link from the registration email.
    # CONFIRM REGISTER resolves the target account from the RPC `source` param
    # (Anope: `na = source.GetAccount()->na`), not from an argument in the
    # command string, so `source` must be set to `nick` here.
    try:
        result = rpc("anope.command", nick, "NickServ", f"CONFIRM REGISTER {code}")
        if _anope_confirmed(result, "has been confirmed"):
            flash("Account confirmed. You can now log in.", "success")
        else:
            flash(result[0] if result else "Confirmation failed.", "error")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("auth.login"))


@bp.route("/confirm/email/<nick>/<code>")
def confirm_email_link(nick, code):
    # Unauthenticated — link from the email-change confirmation email.
    # Same source-resolution requirement as CONFIRM REGISTER above.
    try:
        result = rpc("anope.command", nick, "NickServ", f"CONFIRM EMAIL {code}")
        if _anope_confirmed(result, "has been changed from"):
            flash("Email confirmed successfully. You can now log in.", "success")
        else:
            flash(result[0] if result else "Confirmation failed.", "error")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("auth.login"))


@bp.route("/reset", methods=["GET", "POST"])
def reset():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email_addr = request.form.get("email", "").strip()
        if not username or not email_addr:
            flash("Nick and email are required.", "error")
            return render_template("nickserv/reset.html")
        try:
            # RESETPASS takes both nickname and email as command arguments —
            # it's not identity-based, since the requester isn't logged in.
            rpc("anope.command", None, "NickServ", f"RESETPASS {username} {email_addr}")
            flash("If that account and email match, a reset email has been sent.", "success")
            return redirect(url_for("auth.login"))
        except AnopeError as e:
            flash(e.message, "error")
    return render_template("nickserv/reset.html")


@bp.route("/reset/<nick>/<code>", methods=["GET", "POST"])
def reset_confirm(nick, code):
    if request.method == "POST":
        password = request.form.get("password", "")
        try:
            # CONFIRM RESETPASS only validates the code and (if a live IRC
            # session exists, which RPC has none of) identifies the user —
            # it does NOT set a password. A confirmed reset must be followed
            # by a separate SET PASSWORD call, which works here because
            # source=nick alone is enough for Anope to resolve source.nc
            # (SET PASSWORD has no extra permission requirement beyond that).
            result = rpc("anope.command", None, "NickServ", f"CONFIRM RESETPASS {nick} {code}")
            # CRITICAL: a wrong/expired code comes back as a normal successful
            # RPC reply (see _anope_confirmed docstring) — SET PASSWORD must
            # NOT run unless the confirm step actually succeeded, or anyone
            # could reset anyone's password with a garbage code.
            if not _anope_confirmed(result, "you are now identified as"):
                flash(result[0] if result else "Password reset confirmation failed.", "error")
                return render_template("nickserv/reset_confirm.html", nick=nick, code=code)
            rpc("anope.command", nick, "NickServ", f"SET PASSWORD {password}")
            flash("Password reset successfully. You can now log in.", "success")
            return redirect(url_for("auth.login"))
        except AnopeError as e:
            flash(e.message, "error")
    return render_template("nickserv/reset_confirm.html", nick=nick, code=code)


@bp.route("/email", methods=["GET", "POST"])
@login_required
def email():
    if request.method == "POST":
        new_email = request.form.get("email", "").strip()
        try:
            rpc("anope.command", g.account, "NickServ", f"SET EMAIL {new_email}")
            flash("A confirmation email has been sent to your new address.", "success")
            return redirect(url_for("nickserv.info"))
        except AnopeError as e:
            flash(e.message, "error")
    return render_template("nickserv/email.html")


@bp.route("/password", methods=["GET", "POST"])
@login_required
def password():
    if request.method == "POST":
        old_pw = request.form.get("old_password", "")
        new_pw = request.form.get("new_password", "")
        try:
            rpc("anope.command", g.account, "NickServ", f"SET PASSWORD {new_pw}")
            flash("Password changed successfully.", "success")
            return redirect(url_for("nickserv.info"))
        except AnopeError as e:
            flash(e.message, "error")
    return render_template("nickserv/password.html")


@bp.route("/alist/add", methods=["POST"])
@login_required
def alist_add():
    mask = request.form.get("mask", "").strip()
    if not mask:
        flash("Mask is required.", "error")
        return redirect(url_for("nickserv.alist"))
    try:
        rpc("anope.command", g.account, "NickServ", f"ALIST ADD {mask}")
        flash(f"Added {mask} to access list.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("nickserv.alist"))


@bp.route("/alist/del", methods=["POST"])
@login_required
def alist_del():
    mask = request.form.get("mask", "").strip()
    if not mask:
        flash("Mask is required.", "error")
        return redirect(url_for("nickserv.alist"))
    try:
        rpc("anope.command", g.account, "NickServ", f"ALIST DEL {mask}")
        flash(f"Removed {mask} from access list.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("nickserv.alist"))


# ── SET options (toggles) ─────────────────────────────────────────────────────

@bp.route("/set")
@login_required
def ns_set():
    from utils import parse_ns_info
    info = {}
    account = None
    try:
        result = rpc("anope.command", g.account, "NickServ", f"INFO {g.account}")
        info = parse_ns_info(result)
    except AnopeError as e:
        flash(e.message, "error")
    try:
        account = rpc("anope.account", g.account)
    except AnopeError:
        pass
    return render_template("nickserv/set.html", info=info, account=account)


@bp.route("/set/toggle", methods=["POST"])
@login_required
def ns_set_toggle():
    option = request.form.get("option", "").strip().upper()
    value  = request.form.get("value", "").strip().upper()
    try:
        rpc("anope.command", g.account, "NickServ", f"SET {option} {value}")
        flash(f"{option} set to {value}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("nickserv.ns_set"))


@bp.route("/set/display", methods=["POST"])
@login_required
def ns_set_display():
    nick = request.form.get("nick", "").strip()
    try:
        rpc("anope.command", g.account, "NickServ", f"SET DISPLAY {nick}")
        flash(f"Display nick set to {nick}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("nickserv.ns_set"))


@bp.route("/set/protect", methods=["POST"])
@login_required
def ns_set_protect():
    value = request.form.get("value", "").strip()
    try:
        rpc("anope.command", g.account, "NickServ", f"SET PROTECT {value}")
        flash(f"PROTECT set to {value}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("nickserv.ns_set"))


@bp.route("/set/hide", methods=["POST"])
@login_required
def ns_set_hide():
    what  = request.form.get("what", "").strip().upper()
    value = request.form.get("value", "").strip().upper()
    try:
        rpc("anope.command", g.account, "NickServ", f"SET HIDE {what} {value}")
        flash(f"HIDE {what} set to {value}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("nickserv.ns_set"))


@bp.route("/set/layout", methods=["POST"])
@login_required
def ns_set_layout():
    value = request.form.get("value", "FLEXIBLE").strip().upper()
    try:
        rpc("anope.command", g.account, "NickServ", f"SET LAYOUT {value}")
        flash(f"Layout set to {value}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("nickserv.ns_set"))


@bp.route("/set/timezone", methods=["POST"])
@login_required
def ns_set_timezone():
    tz = request.form.get("timezone", "").strip()
    try:
        rpc("anope.command", g.account, "NickServ", f"SET TIMEZONE {tz}")
        flash(f"Timezone set to {tz}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("nickserv.ns_set"))


@bp.route("/set/text", methods=["POST"])
@login_required
def ns_set_text():
    # Generic handler for SET options that take a free-text value:
    # LANGUAGE, GREET, MASTODON, LOCATION, URL — all share "SET OPTION value" syntax.
    option = request.form.get("option", "").strip().upper()
    if option not in ("LANGUAGE", "GREET", "MASTODON", "LOCATION", "URL"):
        flash("Unknown option.", "error")
        return redirect(url_for("nickserv.ns_set"))
    value = request.form.get("value", "").strip()
    try:
        rpc("anope.command", g.account, "NickServ", f"SET {option} {value}".rstrip())
        flash(f"{option.title()} updated.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("nickserv.ns_set"))


@bp.route("/update", methods=["POST"])
@login_required
def ns_update():
    try:
        rpc("anope.command", g.account, "NickServ", "UPDATE")
        flash("Status updated (memos, channel modes, vhost, userflags refreshed).", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("nickserv.ns_set"))


@bp.route("/recover", methods=["GET", "POST"])
@login_required
def recover():
    # RECOVER/GHOST/RELEASE all alias the same underlying command.
    if request.method == "POST":
        nick = request.form.get("nick", "").strip()
        password = request.form.get("password", "").strip()
        if not nick:
            flash("Nick is required.", "error")
            return render_template("nickserv/recover.html")
        cmd = f"RECOVER {nick} {password}".rstrip()
        try:
            result = rpc("anope.command", g.account, "NickServ", cmd)
            flash(result[0] if result else f"Recovered {nick}.", "success")
        except AnopeError as e:
            flash(e.message, "error")
        return redirect(url_for("nickserv.recover"))
    return render_template("nickserv/recover.html")


@bp.route("/resend", methods=["GET", "POST"])
def resend():
    # Unauthenticated — for an unconfirmed account that never got (or lost) its
    # registration email. AllowUnregistered(true) in Anope, so no login needed.
    if request.method == "POST":
        nick = request.form.get("nick", "").strip()
        try:
            result = rpc("anope.command", nick or None, "NickServ", f"RESEND {nick}".strip())
            flash(result[0] if result else "Confirmation email resent.", "success")
            return redirect(url_for("auth.login"))
        except AnopeError as e:
            flash(e.message, "error")
    return render_template("nickserv/resend.html")


def _oper_required(f):
    from functools import wraps
    from flask import session as flask_session, abort
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not flask_session.get("is_oper"):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


@bp.route("/getemail", methods=["GET", "POST"])
@login_required
@_oper_required
def getemail():
    matches = None
    email_addr = ""
    if request.method == "POST":
        email_addr = request.form.get("email", "").strip()
        try:
            # Real format (confirmed live): one line per match,
            # "Email matched: nick (email) to email."
            result = rpc("anope.command", g.account, "NickServ", f"GETEMAIL {email_addr}")
            import re
            matches = [m.group(1) for line in result
                       if (m := re.match(r'^Email matched:\s+(\S+)', line.strip()))]
        except AnopeError as e:
            flash(e.message, "error")
    return render_template("nickserv/getemail.html", matches=matches, email=email_addr)


# ── AJOIN ─────────────────────────────────────────────────────────────────────

@bp.route("/ajoin")
@login_required
def ajoin():
    from utils import parse_ajoin_list
    try:
        result = rpc("anope.command", g.account, "NickServ", "AJOIN LIST")
        entries = parse_ajoin_list(result)
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    return render_template("nickserv/ajoin.html", entries=entries)


@bp.route("/ajoin/add", methods=["POST"])
@login_required
def ajoin_add():
    channel = request.form.get("channel", "").strip()
    key     = request.form.get("key", "").strip()
    cmd = f"AJOIN ADD {channel}"
    if key:
        cmd += f" {key}"
    try:
        rpc("anope.command", g.account, "NickServ", cmd)
        flash(f"Added {channel} to auto join list.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("nickserv.ajoin"))


@bp.route("/ajoin/del", methods=["POST"])
@login_required
def ajoin_del():
    channel = request.form.get("channel", "").strip()
    try:
        rpc("anope.command", g.account, "NickServ", f"AJOIN DEL {channel}")
        flash(f"Removed {channel} from auto join list.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("nickserv.ajoin"))


# ── UNGROUP ────────────────────────────────────────────────────────────────


@bp.route("/ungroup", methods=["POST"])
@login_required
def ungroup():
    nick = request.form.get("nick", "").strip()
    try:
        rpc("anope.command", g.account, "NickServ", f"UNGROUP {nick}")
        flash(f"{nick} removed from your account.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("nickserv.info"))


# ── DROP ──────────────────────────────────────────────────────────────────────

@bp.route("/drop", methods=["GET", "POST"])
@login_required
def drop():
    if request.method == "POST":
        confirm  = request.form.get("confirm", "").strip()
        password = request.form.get("password", "").strip()
        if confirm != g.account:
            flash("Nick did not match. Drop cancelled.", "error")
            return redirect(url_for("nickserv.drop"))
        try:
            rpc("anope.command", g.account, "NickServ", f"DROP {g.account} {password}")
            flash("Nick dropped.", "success")
            return redirect(url_for("auth.logout"))
        except AnopeError as e:
            flash(e.message, "error")
    return render_template("nickserv/drop.html")


# ── NS LIST (oper) ────────────────────────────────────────────────────────────

@bp.route("/list")
@login_required
def ns_list():
    from utils import parse_ns_list
    pattern = request.args.get("pattern", "*").strip() or "*"
    entries = []
    try:
        result = rpc("anope.command", g.account, "NickServ", f"LIST {pattern}")
        entries = parse_ns_list(result)
    except AnopeError as e:
        flash(e.message, "error")
    return render_template("nickserv/list.html", entries=entries, pattern=pattern)


# ── OPER nick view ────────────────────────────────────────────────────────────
# (_oper_required defined above, next to its first use in getemail())


@bp.route("/oper/<nick>")
@login_required
@_oper_required
def oper_nick(nick):
    from utils import parse_ns_info
    account = None
    ns_info = {}
    try:
        account = rpc("anope.account", nick)
    except AnopeError as e:
        flash(e.message, "error")
    try:
        result = rpc("anope.command", g.account, "NickServ", f"INFO {nick}")
        ns_info = parse_ns_info(result)
    except AnopeError as e:
        flash(e.message, "error")
    return render_template("nickserv/oper_nick.html",
                           target=nick, account=account, ns_info=ns_info)


@bp.route("/oper/<nick>/suspend", methods=["POST"])
@login_required
@_oper_required
def oper_suspend(nick):
    expiry = request.form.get("expiry", "").strip()
    reason = request.form.get("reason", "").strip()
    cmd = f"SUSPEND {nick}"
    if expiry:
        cmd += f" +{expiry}"
    if reason:
        cmd += f" {reason}"
    try:
        rpc("anope.command", g.account, "NickServ", cmd)
        flash(f"{nick} suspended.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("nickserv.oper_nick", nick=nick))


@bp.route("/oper/<nick>/unsuspend", methods=["POST"])
@login_required
@_oper_required
def oper_unsuspend(nick):
    try:
        rpc("anope.command", g.account, "NickServ", f"UNSUSPEND {nick}")
        flash(f"{nick} unsuspended.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("nickserv.oper_nick", nick=nick))


@bp.route("/oper/<nick>/saset/password", methods=["POST"])
@login_required
@_oper_required
def oper_saset_password(nick):
    password = request.form.get("password", "").strip()
    if not password:
        flash("Password is required.", "error")
        return redirect(url_for("nickserv.oper_nick", nick=nick))
    try:
        rpc("anope.command", g.account, "NickServ", f"SASET PASSWORD {nick} {password}")
        flash(f"Password for {nick} changed.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("nickserv.oper_nick", nick=nick))


@bp.route("/oper/<nick>/saset/noexpire", methods=["POST"])
@login_required
@_oper_required
def oper_saset_noexpire(nick):
    value = request.form.get("value", "ON").strip().upper()
    try:
        rpc("anope.command", g.account, "NickServ", f"SASET NOEXPIRE {nick} {value}")
        flash(f"NOEXPIRE for {nick} set to {value}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("nickserv.oper_nick", nick=nick))


@bp.route("/oper/<nick>/drop", methods=["POST"])
@login_required
@_oper_required
def oper_drop(nick):
    confirm = request.form.get("confirm", "").strip()
    if confirm != nick:
        flash("Nick did not match. Drop cancelled.", "error")
        return redirect(url_for("nickserv.oper_nick", nick=nick))
    try:
        rpc("anope.command", g.account, "NickServ", f"DROP {nick} OVERRIDE")
        flash(f"{nick} dropped.", "success")
        return redirect(url_for("nickserv.ns_list"))
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("nickserv.oper_nick", nick=nick))
