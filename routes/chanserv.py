from flask import Blueprint, render_template, request, flash, redirect, url_for, g
from rpc import rpc, AnopeError
from auth import login_required
from utils import (parse_alist, parse_flags_list, parse_akick_view,
                   parse_cs_info, parse_entrymsg_list, parse_log_list,
                   parse_drop_code)

bp = Blueprint("chanserv", __name__, url_prefix="/chanserv")


def _channel_info(channel):
    """Fetch parsed CS INFO for a channel."""
    result = rpc("anope.command", g.account, "ChanServ", f"INFO {channel}")
    return parse_cs_info(result)


# ── Channel list ──────────────────────────────────────────────────────────────

@bp.route("/")
@login_required
def index():
    try:
        result = rpc("anope.command", g.account, "NickServ", "ALIST")
        channels = parse_alist(result)
    except AnopeError as e:
        flash(e.message, "error")
        channels = []
    return render_template("chanserv/index.html", channels=channels)


# ── Access (FLAGS) ────────────────────────────────────────────────────────────

@bp.route("/<channel>/access")
@login_required
def access(channel):
    try:
        result = rpc("anope.command", g.account, "ChanServ", f"FLAGS {channel} LIST * ALL")
        entries = parse_flags_list(result)
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    return render_template("chanserv/access.html", channel=channel, entries=entries)


@bp.route("/<channel>/access/add", methods=["POST"])
@login_required
def access_add(channel):
    mask  = request.form.get("mask", "").strip()
    flags = request.form.get("flags", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"FLAGS {channel} {mask} {flags}")
        flash(f"Updated flags for {mask}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.access", channel=channel))


@bp.route("/<channel>/access/del", methods=["POST"])
@login_required
def access_del(channel):
    mask = request.form.get("mask", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"FLAGS {channel} {mask} -*")
        flash(f"Removed {mask}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.access", channel=channel))


# ── Akick ─────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/akick")
@login_required
def akick(channel):
    try:
        result = rpc("anope.command", g.account, "ChanServ", f"AKICK {channel} VIEW")
        entries = parse_akick_view(result)
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    return render_template("chanserv/akick.html", channel=channel, entries=entries)


@bp.route("/<channel>/akick/add", methods=["POST"])
@login_required
def akick_add(channel):
    mask   = request.form.get("mask", "").strip()
    reason = request.form.get("reason", "").strip()
    cmd = f"AKICK {channel} ADD {mask}"
    if reason:
        cmd += f" {reason}"
    try:
        rpc("anope.command", g.account, "ChanServ", cmd)
        flash(f"Added {mask} to akick list.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.akick", channel=channel))


@bp.route("/<channel>/akick/del", methods=["POST"])
@login_required
def akick_del(channel):
    mask = request.form.get("mask", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"AKICK {channel} DEL {mask}")
        flash(f"Removed {mask}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.akick", channel=channel))


# ── Modes (live channel state) ────────────────────────────────────────────────

@bp.route("/<channel>/modes")
@login_required
def modes(channel):
    try:
        ci = rpc("anope.channel", channel)
    except AnopeError as e:
        flash(e.message, "error")
        ci = None
    return render_template("chanserv/modes.html", channel=channel, ci=ci)


# ── Settings (CS SET) ─────────────────────────────────────────────────────────

@bp.route("/<channel>/set")
@login_required
def set_options(channel):
    try:
        info = _channel_info(channel)
    except AnopeError as e:
        flash(e.message, "error")
        info = {}
    return render_template("chanserv/set.html", channel=channel, info=info)


@bp.route("/<channel>/set/option", methods=["POST"])
@login_required
def set_option(channel):
    option = request.form.get("option", "").strip()
    value  = request.form.get("value", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"SET {channel} {option} {value}")
        flash(f"{option} updated.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.set_options", channel=channel))


@bp.route("/<channel>/set/founder", methods=["POST"])
@login_required
def set_founder(channel):
    founder = request.form.get("founder", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"SET {channel} FOUNDER {founder}")
        flash(f"Founder changed to {founder}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.set_options", channel=channel))


@bp.route("/<channel>/set/successor", methods=["POST"])
@login_required
def set_successor(channel):
    successor = request.form.get("successor", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"SET {channel} SUCCESSOR {successor}")
        flash(f"Successor set to {successor}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.set_options", channel=channel))


@bp.route("/<channel>/set/desc", methods=["POST"])
@login_required
def set_desc(channel):
    desc = request.form.get("desc", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"SET {channel} DESC {desc}")
        flash("Description updated.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.set_options", channel=channel))


@bp.route("/<channel>/set/url", methods=["POST"])
@login_required
def set_url(channel):
    url_val = request.form.get("url", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"SET {channel} URL {url_val}")
        flash("URL updated.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.set_options", channel=channel))


@bp.route("/<channel>/set/email", methods=["POST"])
@login_required
def set_email(channel):
    email = request.form.get("email", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"SET {channel} EMAIL {email}")
        flash("Email updated.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.set_options", channel=channel))


@bp.route("/<channel>/set/bantype", methods=["POST"])
@login_required
def set_bantype(channel):
    bantype = request.form.get("bantype", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"SET {channel} BANTYPE {bantype}")
        flash(f"Ban type set to {bantype}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.set_options", channel=channel))


# ── Entry messages ────────────────────────────────────────────────────────────

@bp.route("/<channel>/entrymsg")
@login_required
def entrymsg(channel):
    try:
        result = rpc("anope.command", g.account, "ChanServ", f"ENTRYMSG {channel} LIST")
        entries = parse_entrymsg_list(result)
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    return render_template("chanserv/entrymsg.html", channel=channel, entries=entries)


@bp.route("/<channel>/entrymsg/add", methods=["POST"])
@login_required
def entrymsg_add(channel):
    msg = request.form.get("message", "").strip()
    if not msg:
        flash("Message is required.", "error")
        return redirect(url_for("chanserv.entrymsg", channel=channel))
    try:
        rpc("anope.command", g.account, "ChanServ", f"ENTRYMSG {channel} ADD {msg}")
        flash("Entry message added.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.entrymsg", channel=channel))


@bp.route("/<channel>/entrymsg/del", methods=["POST"])
@login_required
def entrymsg_del(channel):
    num = request.form.get("num", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"ENTRYMSG {channel} DEL {num}")
        flash("Entry message removed.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.entrymsg", channel=channel))


@bp.route("/<channel>/entrymsg/clear", methods=["POST"])
@login_required
def entrymsg_clear(channel):
    try:
        rpc("anope.command", g.account, "ChanServ", f"ENTRYMSG {channel} CLEAR")
        flash("All entry messages cleared.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.entrymsg", channel=channel))


# ── Log settings ──────────────────────────────────────────────────────────────

@bp.route("/<channel>/log")
@login_required
def log(channel):
    try:
        result = rpc("anope.command", g.account, "ChanServ", f"LOG {channel}")
        entries = parse_log_list(result)
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    return render_template("chanserv/log.html", channel=channel, entries=entries)


@bp.route("/<channel>/log/add", methods=["POST"])
@login_required
def log_add(channel):
    command = request.form.get("command", "").strip()
    method  = request.form.get("method", "").strip()
    status  = request.form.get("status", "").strip()
    cmd = f"LOG {channel} {command} {method}"
    if status:
        cmd += f" {status}"
    try:
        rpc("anope.command", g.account, "ChanServ", cmd)
        flash("Log entry added.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.log", channel=channel))


@bp.route("/<channel>/log/del", methods=["POST"])
@login_required
def log_del(channel):
    command = request.form.get("command", "").strip()
    method  = request.form.get("method", "").strip()
    status  = request.form.get("status", "").strip()
    cmd = f"LOG {channel} {command} {method}"
    if status:
        cmd += f" {status}"
    try:
        rpc("anope.command", g.account, "ChanServ", cmd)
        flash("Log entry removed.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.log", channel=channel))


# ── Invite ────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/invite", methods=["POST"])
@login_required
def invite(channel):
    nick = request.form.get("nick", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"INVITE {channel} {nick}")
        flash(f"Invited {nick} to {channel}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.modes", channel=channel))


# ── Unban ─────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/unban", methods=["POST"])
@login_required
def unban(channel):
    mask = request.form.get("mask", g.account).strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"UNBAN {channel} {mask}")
        flash(f"Unbanned {mask} from {channel}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.modes", channel=channel))


# ── Kick ──────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/kick", methods=["POST"])
@login_required
def kick(channel):
    nick   = request.form.get("nick", "").strip()
    reason = request.form.get("reason", "").strip()
    cmd = f"KICK {channel} {nick}"
    if reason:
        cmd += f" {reason}"
    try:
        rpc("anope.command", g.account, "ChanServ", cmd)
        flash(f"Kicked {nick}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.modes", channel=channel))


# ── Suspend / Unsuspend (oper) ────────────────────────────────────────────────

@bp.route("/<channel>/suspend", methods=["POST"])
@login_required
def suspend(channel):
    reason = request.form.get("reason", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"SUSPEND {channel} {reason}")
        flash(f"{channel} suspended.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.set_options", channel=channel))


@bp.route("/<channel>/unsuspend", methods=["POST"])
@login_required
def unsuspend(channel):
    try:
        rpc("anope.command", g.account, "ChanServ", f"UNSUSPEND {channel}")
        flash(f"{channel} unsuspended.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.set_options", channel=channel))


# ── Drop ──────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/drop", methods=["GET", "POST"])
@login_required
def drop(channel):
    if request.method == "POST":
        confirm = request.form.get("confirm", "").strip()
        if confirm != channel:
            flash("Channel name did not match. Drop cancelled.", "error")
            return redirect(url_for("chanserv.drop", channel=channel))
        try:
            # Step 1: get the confirmation code
            result = rpc("anope.command", g.account, "ChanServ", f"DROP {channel}")
            code = parse_drop_code(result)
            if not code:
                flash("Could not get drop confirmation code.", "error")
                return redirect(url_for("chanserv.drop", channel=channel))
            # Step 2: confirm with code
            rpc("anope.command", g.account, "ChanServ", f"DROP {channel} {code}")
            flash(f"{channel} has been dropped.", "success")
            return redirect(url_for("chanserv.index"))
        except AnopeError as e:
            flash(e.message, "error")
    return render_template("chanserv/drop.html", channel=channel)


# ── GETKEY ────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/getkey", methods=["POST"])
@login_required
def getkey(channel):
    from utils import parse_getkey
    key = None
    try:
        result = rpc("anope.command", g.account, "ChanServ", f"GETKEY {channel}")
        key = parse_getkey(result)
        if key is None:
            flash("No key set or access denied.", "error")
    except AnopeError as e:
        flash(e.message, "error")
    try:
        ci = rpc("anope.channel", channel)
    except AnopeError:
        ci = None
    return render_template("chanserv/modes.html", channel=channel, ci=ci, key=key)


# ── STATUS ────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/status", methods=["POST"])
@login_required
def status(channel):
    from utils import parse_status
    nick = request.form.get("nick", g.account).strip()
    status_result = None
    try:
        result = rpc("anope.command", g.account, "ChanServ", f"STATUS {channel} {nick}")
        status_result = parse_status(result)
    except AnopeError as e:
        flash(e.message, "error")
    try:
        ci = rpc("anope.channel", channel)
    except AnopeError:
        ci = None
    return render_template("chanserv/modes.html",
                           channel=channel, ci=ci, status_result=status_result)


# ── TOPIC ─────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/topic", methods=["POST"])
@login_required
def topic(channel):
    text = request.form.get("topic", "").strip()
    cmd = f"TOPIC {channel}"
    if text:
        cmd += f" {text}"
    try:
        rpc("anope.command", g.account, "ChanServ", cmd)
        flash("Topic updated.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.modes", channel=channel))


# ── MODE ──────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/mode", methods=["POST"])
@login_required
def mode(channel):
    modes = request.form.get("modes", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"MODE {channel} {modes}")
        flash(f"Mode {modes} set.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.modes", channel=channel))


# ── BAN ───────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/ban", methods=["POST"])
@login_required
def ban(channel):
    mask   = request.form.get("mask", "").strip()
    reason = request.form.get("reason", "").strip()
    cmd = f"BAN {channel} {mask}"
    if reason:
        cmd += f" {reason}"
    try:
        rpc("anope.command", g.account, "ChanServ", cmd)
        flash(f"Banned {mask}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.modes", channel=channel))


# ── SYNC ──────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/sync", methods=["POST"])
@login_required
def sync(channel):
    try:
        rpc("anope.command", g.account, "ChanServ", f"SYNC {channel}")
        flash(f"{channel} synced.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.modes", channel=channel))


# ── ENFORCE ───────────────────────────────────────────────────────────────────

@bp.route("/<channel>/enforce", methods=["POST"])
@login_required
def enforce(channel):
    what = request.form.get("what", "").strip()
    cmd = f"ENFORCE {channel}"
    if what:
        cmd += f" {what}"
    try:
        result = rpc("anope.command", g.account, "ChanServ", cmd)
        flash(" ".join(result) if result else "Enforced.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.modes", channel=channel))


# ── Status commands (OP/DEOP/VOICE/etc.) ─────────────────────────────────────

STATUS_CMDS = ["OP", "DEOP", "HALFOP", "DEHALFOP", "VOICE", "DEVOICE",
               "PROTECT", "DEPROTECT", "OWNER", "DEOWNER"]

@bp.route("/<channel>/chstatus", methods=["POST"])
@login_required
def chstatus(channel):
    cmd  = request.form.get("cmd", "").strip().upper()
    nick = request.form.get("nick", g.account).strip()
    if cmd not in STATUS_CMDS:
        flash("Invalid command.", "error")
        return redirect(url_for("chanserv.modes", channel=channel))
    try:
        rpc("anope.command", g.account, "ChanServ", f"{cmd} {channel} {nick}")
        flash(f"{cmd} applied to {nick}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.modes", channel=channel))


# ── STATS ─────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/stats")
@login_required
def stats(channel):
    from utils import parse_stats
    my_stats = None
    try:
        result = rpc("anope.command", g.account, "ChanServ", f"STATS {channel}")
        my_stats = parse_stats(result)
    except AnopeError as e:
        flash(e.message, "error")
    return render_template("chanserv/stats.html", channel=channel, stats=my_stats)


# ── CLONE ─────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/clone", methods=["GET", "POST"])
@login_required
def clone(channel):
    from utils import parse_clone_result
    result = None
    if request.method == "POST":
        target = request.form.get("target", "").strip()
        what   = request.form.get("what", "").strip()
        cmd = f"CLONE {channel} {target}"
        if what:
            cmd += f" {what}"
        try:
            lines = rpc("anope.command", g.account, "ChanServ", cmd)
            result = parse_clone_result(lines)
            flash("Clone completed.", "success")
        except AnopeError as e:
            flash(e.message, "error")
    return render_template("chanserv/clone.html", channel=channel, result=result)


# ── LIST ──────────────────────────────────────────────────────────────────────

@bp.route("/list")
@login_required
def cs_list():
    from utils import parse_cs_list
    pattern  = request.args.get("pattern", "*").strip() or "*"
    extra    = request.args.get("extra", "").strip()   # SUSPENDED / NOEXPIRE for opers
    cmd = f"LIST {pattern}"
    if extra:
        cmd += f" {extra}"
    channels = []
    try:
        result = rpc("anope.command", g.account, "ChanServ", cmd)
        channels = parse_cs_list(result)
    except AnopeError as e:
        flash(e.message, "error")
    return render_template("chanserv/list.html",
                           channels=channels, pattern=pattern, extra=extra)
