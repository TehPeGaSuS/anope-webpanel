from flask import Blueprint, render_template, request, flash, redirect, url_for, g
from urllib.parse import unquote
from rpc import rpc, AnopeError
from auth import login_required
from utils import parse_bs_info, parse_bs_botlist, parse_bs_badwords

bp = Blueprint("botserv", __name__, url_prefix="/botserv")

KICKERS = [
    ("BADWORDS", "Bad words"),
    ("BOLDS", "Bolds"),
    ("CAPS", "Caps"),
    ("COLORS", "Colors"),
    ("FLOOD", "Flood"),
    ("ITALICS", "Italics"),
    ("REPEAT", "Repeat"),
    ("REVERSES", "Reverses"),
    ("UNDERLINES", "Underlines"),
    ("AMSG", "AMSG"),
]


def chan(channel):
    """URLs carry the channel without '#' (avoids %23) — add it back for RPC."""
    channel = unquote(channel)
    if not channel.startswith("#"):
        channel = "#" + channel
    return channel


def chanurl(channel):
    return channel.lstrip("#")


def oper_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        from flask import session as flask_session, abort
        if not flask_session.get("is_oper"):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


@bp.route("/<channel>/")
@login_required
def index(channel):
    try:
        result = rpc("anope.command", g.account, "BotServ", f"INFO {chan(channel)}")
        info = parse_bs_info(result)
    except AnopeError as e:
        flash(e.message, "error")
        info = {}
    return render_template("botserv/index.html", channel=chan(channel), info=info, kickers=KICKERS)


@bp.route("/<channel>/assign", methods=["POST"])
@login_required
def assign(channel):
    botnick = request.form.get("botnick", "").strip()
    if not botnick:
        flash("Bot nick is required.", "error")
        return redirect(url_for("botserv.index", channel=chanurl(chan(channel))))
    try:
        rpc("anope.command", g.account, "BotServ", f"ASSIGN {chan(channel)} {botnick}")
        flash(f"{botnick} assigned to {chan(channel)}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("botserv.index", channel=chanurl(chan(channel))))


@bp.route("/<channel>/unassign", methods=["POST"])
@login_required
def unassign(channel):
    try:
        rpc("anope.command", g.account, "BotServ", f"UNASSIGN {chan(channel)}")
        flash(f"Bot unassigned from {chan(channel)}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("botserv.index", channel=chanurl(chan(channel))))


@bp.route("/<channel>/kick/<option>", methods=["POST"])
@login_required
def kick_set(channel, option):
    option = option.upper()
    if option not in dict(KICKERS):
        flash("Unknown kicker.", "error")
        return redirect(url_for("botserv.index", channel=chanurl(chan(channel))))
    state = request.form.get("state", "OFF").upper()
    ttb = request.form.get("ttb", "").strip()
    extra = request.form.get("extra", "").strip()
    args = " ".join(x for x in (ttb, extra) if x)
    cmd = f"KICK {option} {chan(channel)} {state} {args}".rstrip()
    try:
        result = rpc("anope.command", g.account, "BotServ", cmd)
        flash(result[0] if result else "Kicker updated.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("botserv.index", channel=chanurl(chan(channel))))


@bp.route("/<channel>/set/<option>", methods=["POST"])
@login_required
def set_option(channel, option):
    option = option.upper()
    if option not in ("DONTKICKOPS", "DONTKICKVOICES", "FANTASY", "GREET", "BANEXPIRE", "NOBOT"):
        flash("Unknown option.", "error")
        return redirect(url_for("botserv.index", channel=chanurl(chan(channel))))
    if option == "BANEXPIRE":
        value = request.form.get("value", "0").strip() or "0"
    else:
        value = request.form.get("state", "OFF").upper()
    try:
        result = rpc("anope.command", g.account, "BotServ", f"SET {option} {chan(channel)} {value}")
        flash(result[0] if result else "Setting updated.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("botserv.index", channel=chanurl(chan(channel))))


@bp.route("/<channel>/say", methods=["POST"])
@login_required
def say(channel):
    text = request.form.get("text", "").strip()
    if not text:
        flash("Message text is required.", "error")
        return redirect(url_for("botserv.index", channel=chanurl(chan(channel))))
    try:
        rpc("anope.command", g.account, "BotServ", f"SAY {chan(channel)} {text}")
        flash("Message sent.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("botserv.index", channel=chanurl(chan(channel))))


@bp.route("/<channel>/act", methods=["POST"])
@login_required
def act(channel):
    text = request.form.get("text", "").strip()
    if not text:
        flash("Action text is required.", "error")
        return redirect(url_for("botserv.index", channel=chanurl(chan(channel))))
    try:
        rpc("anope.command", g.account, "BotServ", f"ACT {chan(channel)} {text}")
        flash("Action sent.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("botserv.index", channel=chanurl(chan(channel))))


# ── Bad words ────────────────────────────────────────────────────────────────

@bp.route("/<channel>/badwords")
@login_required
def badwords(channel):
    try:
        result = rpc("anope.command", g.account, "BotServ", f"BADWORDS {chan(channel)} LIST")
        entries = parse_bs_badwords(result)
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    return render_template("botserv/badwords.html", channel=chan(channel), entries=entries)


@bp.route("/<channel>/badwords/add", methods=["POST"])
@login_required
def badwords_add(channel):
    word = request.form.get("word", "").strip()
    kind = request.form.get("kind", "").strip().upper()
    if not word:
        flash("Word is required.", "error")
        return redirect(url_for("botserv.badwords", channel=chanurl(chan(channel))))
    cmd = f"BADWORDS {chan(channel)} ADD {word}" + (f" {kind}" if kind in ("SINGLE", "START", "END") else "")
    try:
        rpc("anope.command", g.account, "BotServ", cmd)
        flash(f"{word} added to the bad words list.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("botserv.badwords", channel=chanurl(chan(channel))))


@bp.route("/<channel>/badwords/del", methods=["POST"])
@login_required
def badwords_del(channel):
    num = request.form.get("num", "").strip()
    try:
        rpc("anope.command", g.account, "BotServ", f"BADWORDS {chan(channel)} DEL {num}")
        flash("Removed from the bad words list.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("botserv.badwords", channel=chanurl(chan(channel))))


@bp.route("/<channel>/badwords/clear", methods=["POST"])
@login_required
def badwords_clear(channel):
    try:
        rpc("anope.command", g.account, "BotServ", f"BADWORDS {chan(channel)} CLEAR")
        flash("Bad words list cleared.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("botserv.badwords", channel=chanurl(chan(channel))))


# ── Oper: network bot list / management ─────────────────────────────────────

@bp.route("/bots")
@login_required
@oper_required
def bots():
    try:
        result = rpc("anope.command", g.account, "BotServ", "BOTLIST")
        entries = parse_bs_botlist(result)
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    return render_template("botserv/bots.html", entries=entries)


@bp.route("/bots/add", methods=["POST"])
@login_required
@oper_required
def bots_add():
    nick = request.form.get("nick", "").strip()
    user = request.form.get("user", "").strip()
    host = request.form.get("host", "").strip()
    real = request.form.get("real", "").strip()
    if not all((nick, user, host, real)):
        flash("Nick, user, host, and realname are all required.", "error")
        return redirect(url_for("botserv.bots"))
    try:
        rpc("anope.command", g.account, "BotServ", f"BOT ADD {nick} {user} {host} {real}")
        flash(f"{nick} added to the bot list.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("botserv.bots"))


@bp.route("/bots/change", methods=["POST"])
@login_required
@oper_required
def bots_change():
    oldnick = request.form.get("oldnick", "").strip()
    newnick = request.form.get("newnick", "").strip()
    user = request.form.get("user", "").strip()
    host = request.form.get("host", "").strip()
    real = request.form.get("real", "").strip()
    if not oldnick or not newnick:
        flash("Current and new nick are required.", "error")
        return redirect(url_for("botserv.bots"))
    extra = " ".join(x for x in (user, host, real) if x)
    cmd = f"BOT CHANGE {oldnick} {newnick}" + (f" {extra}" if extra else "")
    try:
        rpc("anope.command", g.account, "BotServ", cmd)
        flash(f"{oldnick} renamed to {newnick}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("botserv.bots"))


@bp.route("/bots/del", methods=["POST"])
@login_required
@oper_required
def bots_del():
    nick = request.form.get("nick", "").strip()
    try:
        rpc("anope.command", g.account, "BotServ", f"BOT DEL {nick}")
        flash(f"{nick} deleted.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("botserv.bots"))


@bp.route("/bots/private", methods=["POST"])
@login_required
@oper_required
def bots_private():
    nick = request.form.get("nick", "").strip()
    state = request.form.get("state", "OFF").upper()
    try:
        rpc("anope.command", g.account, "BotServ", f"SET PRIVATE {nick} {state}")
        flash(f"{nick} private set to {state}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("botserv.bots"))
