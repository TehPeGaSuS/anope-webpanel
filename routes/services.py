from flask import Blueprint, render_template, request, flash, redirect, url_for, g
from rpc import rpc, AnopeError
from auth import login_required
from utils import parse_memo_list

# ---------- MemoServ ----------

memo_bp = Blueprint("memoserv", __name__, url_prefix="/memoserv")


@memo_bp.route("/")
@login_required
def index():
    try:
        result = rpc("anope.command", g.account, "MemoServ", "LIST")
        memos = parse_memo_list(result)
    except AnopeError as e:
        flash(e.message, "error")
        memos = []
    try:
        info = rpc("anope.command", g.account, "MemoServ", "INFO")
    except AnopeError:
        info = []
    return render_template("memoserv/index.html", memos=memos, info=info)


@memo_bp.route("/read/<int:num>")
@login_required
def read(num):
    try:
        result = rpc("anope.command", g.account, "MemoServ", f"READ {num}")
        # Strip header/footer lines, keep content
        lines = [l.replace('', '').strip() for l in result
                 if l.strip() and not l.strip().startswith("Memo") and not l.strip().startswith("There")]
    except AnopeError as e:
        flash(e.message, "error")
        lines = []
    return render_template("memoserv/read.html", lines=lines, num=num)


@memo_bp.route("/send", methods=["GET", "POST"])
@login_required
def send():
    if request.method == "POST":
        target = request.form.get("target", "").strip()
        message = request.form.get("message", "").strip()
        if not target or not message:
            flash("Target and message are required.", "error")
        else:
            try:
                rpc("anope.command", g.account, "MemoServ", f"SEND {target} {message}")
                flash(f"Memo sent to {target}.", "success")
                return redirect(url_for("memoserv.index"))
            except AnopeError as e:
                flash(e.message, "error")
    return render_template("memoserv/send.html")


@memo_bp.route("/del", methods=["POST"])
@login_required
def delete():
    num = request.form.get("num", "").strip()
    try:
        rpc("anope.command", g.account, "MemoServ", f"DEL {num}")
        flash("Memo deleted.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("memoserv.index"))


@memo_bp.route("/cancel", methods=["POST"])
@login_required
def cancel():
    target = request.form.get("target", "").strip()
    try:
        rpc("anope.command", g.account, "MemoServ", f"CANCEL {target}")
        flash(f"Cancelled your last unread memo to {target}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("memoserv.index"))


@memo_bp.route("/check", methods=["POST"])
@login_required
def check():
    nick = request.form.get("nick", "").strip()
    try:
        result = rpc("anope.command", g.account, "MemoServ", f"CHECK {nick}")
        flash(result[0] if result else f"Checked {nick}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("memoserv.index"))


@memo_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        action = request.form.get("action", "")
        try:
            if action == "notify":
                value = request.form.get("value", "ON").upper()
                rpc("anope.command", g.account, "MemoServ", f"SET NOTIFY {value}")
                flash(f"Notify set to {value}.", "success")
            elif action == "limit":
                value = request.form.get("value", "").strip() or "NONE"
                rpc("anope.command", g.account, "MemoServ", f"SET LIMIT {value}")
                flash(f"Limit set to {value}.", "success")
        except AnopeError as e:
            flash(e.message, "error")
        return redirect(url_for("memoserv.settings"))
    return render_template("memoserv/settings.html")


# ---------- MemoServ: ignore list ----------

@memo_bp.route("/ignore")
@login_required
def ignore():
    try:
        result = rpc("anope.command", g.account, "MemoServ", "IGNORE LIST")
        entries = [l.strip() for l in result
                   if l.strip() and not l.strip().lower().startswith("memo ignore list")]
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    return render_template("memoserv/ignore.html", entries=entries)


@memo_bp.route("/ignore/add", methods=["POST"])
@login_required
def ignore_add():
    entry = request.form.get("entry", "").strip()
    if not entry:
        flash("Nick or mask is required.", "error")
        return redirect(url_for("memoserv.ignore"))
    try:
        rpc("anope.command", g.account, "MemoServ", f"IGNORE ADD {entry}")
        flash(f"{entry} added to your memo ignore list.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("memoserv.ignore"))


@memo_bp.route("/ignore/del", methods=["POST"])
@login_required
def ignore_del():
    entry = request.form.get("entry", "").strip()
    try:
        rpc("anope.command", g.account, "MemoServ", f"IGNORE DEL {entry}")
        flash(f"{entry} removed from your memo ignore list.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("memoserv.ignore"))


# ---------- MemoServ: oper ----------

def _oper_required(f):
    from functools import wraps
    from flask import session as flask_session, abort
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not flask_session.get("is_oper"):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


@memo_bp.route("/sendall", methods=["GET", "POST"])
@login_required
@_oper_required
def sendall():
    if request.method == "POST":
        text = request.form.get("text", "").strip()
        if not text:
            flash("Memo text is required.", "error")
        else:
            try:
                rpc("anope.command", g.account, "MemoServ", f"SENDALL {text}")
                flash("Memo sent to all registered users.", "success")
            except AnopeError as e:
                flash(e.message, "error")
    return render_template("memoserv/sendall.html")


@memo_bp.route("/staff", methods=["GET", "POST"])
@login_required
@_oper_required
def staff():
    if request.method == "POST":
        text = request.form.get("text", "").strip()
        if not text:
            flash("Memo text is required.", "error")
        else:
            try:
                rpc("anope.command", g.account, "MemoServ", f"STAFF {text}")
                flash("Memo sent to all services staff.", "success")
            except AnopeError as e:
                flash(e.message, "error")
    return render_template("memoserv/staff.html")


# ---------- HostServ ----------

host_bp = Blueprint("hostserv", __name__, url_prefix="/hostserv")


def _hs_oper_required(f):
    """Decorator: 403 if not oper."""
    from functools import wraps
    from flask import session as flask_session, abort
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not flask_session.get("is_oper"):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


@host_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        vhost = request.form.get("vhost", "").strip()
        if not vhost:
            flash("VHost is required.", "error")
        else:
            try:
                rpc("anope.command", g.account, "HostServ", f"REQUEST {vhost}")
                flash("VHost request submitted.", "success")
                return redirect(url_for("hostserv.index"))
            except AnopeError as e:
                flash(e.message, "error")
    try:
        account = rpc("anope.account", g.account)
    except AnopeError as e:
        flash(e.message, "error")
        account = None
    return render_template("hostserv/index.html", account=account)


@host_bp.route("/on", methods=["POST"])
@login_required
def on():
    try:
        rpc("anope.command", g.account, "HostServ", "ON")
        flash("VHost activated.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("hostserv.index"))


@host_bp.route("/off", methods=["POST"])
@login_required
def off():
    try:
        rpc("anope.command", g.account, "HostServ", "OFF")
        flash("VHost deactivated.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("hostserv.index"))


@host_bp.route("/group", methods=["POST"])
@login_required
def group():
    try:
        rpc("anope.command", g.account, "HostServ", "GROUP")
        flash("VHost synced to all grouped nicks.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("hostserv.index"))


@host_bp.route("/offerlist", methods=["GET", "POST"])
@login_required
def offerlist():
    from utils import parse_hs_offerlist
    if request.method == "POST":
        choice = request.form.get("choice", "").strip()
        if not choice:
            flash("Select an offer to take.", "error")
        else:
            try:
                rpc("anope.command", g.account, "HostServ", f"OFFERLIST TAKE {choice}")
                flash("VHost taken from offer list.", "success")
                return redirect(url_for("hostserv.index"))
            except AnopeError as e:
                flash(e.message, "error")
    offers = []
    try:
        result = rpc("anope.command", g.account, "HostServ", "OFFERLIST")
        offers = parse_hs_offerlist(result)
    except AnopeError as e:
        flash(e.message, "error")
    return render_template("hostserv/offerlist.html", offers=offers)


# ── Oper-only management ──────────────────────────────────────────────────

@host_bp.route("/admin")
@login_required
@_hs_oper_required
def admin():
    from utils import parse_hs_list
    pattern = request.args.get("pattern", "").strip()
    entries = []
    try:
        cmd = f"LIST {pattern}" if pattern else "LIST"
        result = rpc("anope.command", g.account, "HostServ", cmd)
        entries = parse_hs_list(result)
    except AnopeError as e:
        flash(e.message, "error")
    return render_template("hostserv/admin.html", entries=entries, pattern=pattern)


@host_bp.route("/admin/waiting")
@login_required
@_hs_oper_required
def waiting():
    from utils import parse_hs_list
    entries = []
    try:
        result = rpc("anope.command", g.account, "HostServ", "WAITING")
        entries = parse_hs_list(result)
    except AnopeError as e:
        flash(e.message, "error")
    return render_template("hostserv/waiting.html", entries=entries)


@host_bp.route("/admin/activate", methods=["POST"])
@login_required
@_hs_oper_required
def activate():
    nick = request.form.get("nick", "").strip()
    try:
        rpc("anope.command", g.account, "HostServ", f"ACTIVATE {nick}")
        flash(f"VHost for {nick} activated.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(request.referrer or url_for("hostserv.waiting"))


@host_bp.route("/admin/reject", methods=["POST"])
@login_required
@_hs_oper_required
def reject():
    nick = request.form.get("nick", "").strip()
    reason = request.form.get("reason", "").strip()
    cmd = f"REJECT {nick}"
    if reason:
        cmd += f" {reason}"
    try:
        rpc("anope.command", g.account, "HostServ", cmd)
        flash(f"VHost request for {nick} rejected.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(request.referrer or url_for("hostserv.waiting"))


@host_bp.route("/admin/set", methods=["POST"])
@login_required
@_hs_oper_required
def set_vhost():
    nick = request.form.get("nick", "").strip()
    hostmask = request.form.get("hostmask", "").strip()
    if not nick or not hostmask:
        flash("Nick and hostmask are required.", "error")
        return redirect(url_for("hostserv.admin"))
    try:
        rpc("anope.command", g.account, "HostServ", f"SET {nick} {hostmask}")
        flash(f"VHost for {nick} set.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("hostserv.admin"))


@host_bp.route("/admin/setall", methods=["POST"])
@login_required
@_hs_oper_required
def setall():
    nick = request.form.get("nick", "").strip()
    hostmask = request.form.get("hostmask", "").strip()
    if not nick or not hostmask:
        flash("Nick and hostmask are required.", "error")
        return redirect(url_for("hostserv.admin"))
    try:
        rpc("anope.command", g.account, "HostServ", f"SETALL {nick} {hostmask}")
        flash(f"VHost for {nick} and all grouped nicks set.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("hostserv.admin"))


@host_bp.route("/admin/del", methods=["POST"])
@login_required
@_hs_oper_required
def delete_vhost():
    nick = request.form.get("nick", "").strip()
    try:
        rpc("anope.command", g.account, "HostServ", f"DEL {nick}")
        flash(f"VHost for {nick} deleted.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("hostserv.admin"))


@host_bp.route("/admin/delall", methods=["POST"])
@login_required
@_hs_oper_required
def delall():
    nick = request.form.get("nick", "").strip()
    try:
        rpc("anope.command", g.account, "HostServ", f"DELALL {nick}")
        flash(f"VHost for {nick} and all grouped nicks deleted.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("hostserv.admin"))


@host_bp.route("/admin/offer", methods=["GET", "POST"])
@login_required
@_hs_oper_required
def offer():
    from utils import parse_hs_offerlist
    if request.method == "POST":
        action = request.form.get("action", "").strip().upper()
        if action == "ADD":
            vhost = request.form.get("vhost", "").strip()
            expiry = request.form.get("expiry", "").strip()
            reason = request.form.get("reason", "").strip()
            cmd = "OFFER ADD"
            if expiry:
                cmd += f" +{expiry}"
            cmd += f" {vhost}"
            if reason:
                cmd += f" {reason}"
            try:
                rpc("anope.command", g.account, "HostServ", cmd)
                flash(f"VHost offer {vhost} added.", "success")
            except AnopeError as e:
                flash(e.message, "error")
        elif action == "DEL":
            target = request.form.get("target", "").strip()
            try:
                rpc("anope.command", g.account, "HostServ", f"OFFER DEL {target}")
                flash(f"Offer {target} removed.", "success")
            except AnopeError as e:
                flash(e.message, "error")
        elif action == "CLEAR":
            try:
                rpc("anope.command", g.account, "HostServ", "OFFER CLEAR")
                flash("Host offer list cleared.", "success")
            except AnopeError as e:
                flash(e.message, "error")
        return redirect(url_for("hostserv.offer"))

    offers = []
    try:
        result = rpc("anope.command", g.account, "HostServ", "OFFER LIST")
        offers = parse_hs_offerlist(result)
    except AnopeError as e:
        flash(e.message, "error")
    return render_template("hostserv/offer.html", offers=offers)
