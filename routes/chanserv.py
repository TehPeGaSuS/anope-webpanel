from flask import Blueprint, render_template, request, flash, redirect, url_for, g
from urllib.parse import unquote
from rpc import rpc, AnopeError
from auth import login_required
from utils import (parse_alist, parse_flags_list, parse_akick_view,
                   parse_cs_info, parse_entrymsg_list, parse_log_list,
                   parse_drop_code)

bp = Blueprint("chanserv", __name__, url_prefix="/chanserv")


def chan(channel):
    """
    Decode channel name from URL segment.
    URLs use the channel name WITHOUT the leading #
    (e.g. /chanserv/PTirc/access) to avoid %23 encoding.
    We add the # back here for use in RPC calls.
    """
    channel = unquote(channel)
    if not channel.startswith("#"):
        channel = "#" + channel
    return channel


def chanurl(channel):
    """Strip leading # for use in url_for() calls."""
    return channel.lstrip("#")


def _channel_info(channel):
    """Fetch parsed CS INFO for a channel."""
    result = rpc("anope.command", g.account, "ChanServ", f"INFO {chan(channel)}")
    return parse_cs_info(result)


def _modes_render(channel, ci, page=1, key=None, status_result=None):
    """Build paginated render_template call for modes.html."""
    per_page = 100
    users_page = []
    total_users = 0
    if ci and ci.get("users"):
        total_users = len(ci["users"])
        start = (page - 1) * per_page
        users_page = ci["users"][start:start + per_page]
    total_pages = max(1, (total_users + per_page - 1) // per_page)
    return render_template("chanserv/modes.html",
                           channel=chan(channel), ci=ci,
                           users_page=users_page, page=page,
                           total_pages=total_pages, total_users=total_users,
                           key=key, status_result=status_result)


# ── Channel list ──────────────────────────────────────────────────────────────

@bp.route("/")
@login_required
def index():
    from flask import session as flask_session
    try:
        result = rpc("anope.command", g.account, "NickServ", "ALIST")
        channels = parse_alist(result)
        # Cache in session for the channel bar
        flask_session["chanserv_channels"] = channels
    except AnopeError as e:
        flash(e.message, "error")
        channels = []
    return render_template("chanserv/index.html", channels=channels)


# ── Access (FLAGS) ────────────────────────────────────────────────────────────

@bp.route("/<channel>/access")
@login_required
def access(channel):
    try:
        result = rpc("anope.command", g.account, "ChanServ", f"FLAGS {chan(channel)} LIST * ALL")
        # DEBUG: Log raw response for troubleshooting
        import sys
        print(f"[DEBUG] FLAGS LIST response for {chan(channel)}:", file=sys.stderr)
        print(f"[DEBUG] Raw result type: {type(result)}", file=sys.stderr)
        print(f"[DEBUG] Raw result: {result}", file=sys.stderr)
        if isinstance(result, list):
            for i, line in enumerate(result):
                print(f"[DEBUG]   Line {i}: {repr(line)}", file=sys.stderr)
        entries = parse_flags_list(result)
        print(f"[DEBUG] Parsed {len(entries)} entries", file=sys.stderr)
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    return render_template("chanserv/access.html", channel=chan(channel), entries=entries)


@bp.route("/<channel>/access/add", methods=["POST"])
@login_required
def access_add(channel):
    mask  = request.form.get("mask", "").strip()
    flags = request.form.get("flags", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"FLAGS {chan(channel)} {mask} {flags}")
        flash(f"Updated flags for {mask}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.access", channel=chanurl(chan(channel))))


@bp.route("/<channel>/access/del", methods=["POST"])
@login_required
def access_del(channel):
    mask = request.form.get("mask", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"FLAGS {chan(channel)} {mask} -*")
        flash(f"Removed {mask}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.access", channel=chanurl(chan(channel))))


# ── Akick ─────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/akick")
@login_required
def akick(channel):
    try:
        result = rpc("anope.command", g.account, "ChanServ", f"AKICK {chan(channel)} VIEW")
        # DEBUG: Log raw response for troubleshooting
        import sys
        print(f"[DEBUG] AKICK VIEW response for {chan(channel)}:", file=sys.stderr)
        print(f"[DEBUG] Raw result type: {type(result)}", file=sys.stderr)
        print(f"[DEBUG] Raw result: {result}", file=sys.stderr)
        if isinstance(result, list):
            for i, line in enumerate(result):
                print(f"[DEBUG]   Line {i}: {repr(line)}", file=sys.stderr)
        entries = parse_akick_view(result)
        print(f"[DEBUG] Parsed {len(entries)} entries", file=sys.stderr)
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    return render_template("chanserv/akick.html", channel=chan(channel), entries=entries)


@bp.route("/<channel>/akick/add", methods=["POST"])
@login_required
def akick_add(channel):
    mask   = request.form.get("mask", "").strip()
    reason = request.form.get("reason", "").strip()
    cmd = f"AKICK {chan(channel)} ADD {mask}"
    if reason:
        cmd += f" {reason}"
    try:
        rpc("anope.command", g.account, "ChanServ", cmd)
        flash(f"Added {mask} to akick list.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.akick", channel=chanurl(chan(channel))))


@bp.route("/<channel>/akick/del", methods=["POST"])
@login_required
def akick_del(channel):
    mask = request.form.get("mask", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"AKICK {chan(channel)} DEL {mask}")
        flash(f"Removed {mask}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.akick", channel=chanurl(chan(channel))))


# ── Modes (live channel state) ────────────────────────────────────────────────

@bp.route("/<channel>/modes")
@login_required
def modes(channel):
    page = max(1, int(request.args.get("page", 1)))
    ci = None
    try:
        ci = rpc("anope.channel", chan(channel))
    except AnopeError as e:
        flash(e.message, "error")
    return _modes_render(channel, ci, page=page)


# ── Settings (CS SET) ─────────────────────────────────────────────────────────

@bp.route("/<channel>/set")
@login_required
def set_options(channel):
    try:
        info = _channel_info(channel)
    except AnopeError as e:
        flash(e.message, "error")
        info = {}
    return render_template("chanserv/set.html", channel=chan(channel), info=info)


@bp.route("/<channel>/set/option", methods=["POST"])
@login_required
def set_option(channel):
    option = request.form.get("option", "").strip()
    value  = request.form.get("value", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"SET {option} {chan(channel)} {value}")
        flash(f"{option} updated.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.set_options", channel=chanurl(chan(channel))))


@bp.route("/<channel>/set/founder", methods=["POST"])
@login_required
def set_founder(channel):
    founder = request.form.get("founder", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"SET FOUNDER {chan(channel)} {founder}")
        flash(f"Founder changed to {founder}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.set_options", channel=chanurl(chan(channel))))


@bp.route("/<channel>/set/successor", methods=["POST"])
@login_required
def set_successor(channel):
    successor = request.form.get("successor", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"SET SUCCESSOR {chan(channel)} {successor}")
        flash(f"Successor set to {successor}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.set_options", channel=chanurl(chan(channel))))


@bp.route("/<channel>/set/desc", methods=["POST"])
@login_required
def set_desc(channel):
    desc = request.form.get("desc", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"SET DESCRIPTION {chan(channel)} {desc}")
        flash("Description updated.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.set_options", channel=chanurl(chan(channel))))


@bp.route("/<channel>/set/url", methods=["POST"])
@login_required
def set_url(channel):
    url_val = request.form.get("url", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"SET URL {chan(channel)} {url_val}")
        flash("URL updated.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.set_options", channel=chanurl(chan(channel))))


@bp.route("/<channel>/set/email", methods=["POST"])
@login_required
def set_email(channel):
    email = request.form.get("email", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"SET EMAIL {chan(channel)} {email}")
        flash("Email updated.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.set_options", channel=chanurl(chan(channel))))


@bp.route("/<channel>/set/bantype", methods=["POST"])
@login_required
def set_bantype(channel):
    bantype = request.form.get("bantype", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"SET BANTYPE {chan(channel)} {bantype}")
        flash(f"Ban type set to {bantype}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.set_options", channel=chanurl(chan(channel))))


# ── Entry messages ────────────────────────────────────────────────────────────

@bp.route("/<channel>/entrymsg")
@login_required
def entrymsg(channel):
    try:
        result = rpc("anope.command", g.account, "ChanServ", f"ENTRYMSG {chan(channel)} LIST")
        entries = parse_entrymsg_list(result)
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    return render_template("chanserv/entrymsg.html", channel=chan(channel), entries=entries)


@bp.route("/<channel>/entrymsg/add", methods=["POST"])
@login_required
def entrymsg_add(channel):
    msg = request.form.get("message", "").strip()
    if not msg:
        flash("Message is required.", "error")
        return redirect(url_for("chanserv.entrymsg", channel=chanurl(chan(channel))))
    try:
        rpc("anope.command", g.account, "ChanServ", f"ENTRYMSG {chan(channel)} ADD {msg}")
        flash("Entry message added.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.entrymsg", channel=chanurl(chan(channel))))


@bp.route("/<channel>/entrymsg/del", methods=["POST"])
@login_required
def entrymsg_del(channel):
    num = request.form.get("num", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"ENTRYMSG {chan(channel)} DEL {num}")
        flash("Entry message removed.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.entrymsg", channel=chanurl(chan(channel))))


@bp.route("/<channel>/entrymsg/clear", methods=["POST"])
@login_required
def entrymsg_clear(channel):
    try:
        rpc("anope.command", g.account, "ChanServ", f"ENTRYMSG {chan(channel)} CLEAR")
        flash("All entry messages cleared.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.entrymsg", channel=chanurl(chan(channel))))


# ── Log settings ──────────────────────────────────────────────────────────────

@bp.route("/<channel>/log")
@login_required
def log(channel):
    try:
        result = rpc("anope.command", g.account, "ChanServ", f"LOG {chan(channel)}")
        entries = parse_log_list(result)
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    return render_template("chanserv/log.html", channel=chan(channel), entries=entries)


@bp.route("/<channel>/log/add", methods=["POST"])
@login_required
def log_add(channel):
    command = request.form.get("command", "").strip()
    method  = request.form.get("method", "").strip()
    status  = request.form.get("status", "").strip()
    cmd = f"LOG {chan(channel)} {command} {method}"
    if status:
        cmd += f" {status}"
    try:
        rpc("anope.command", g.account, "ChanServ", cmd)
        flash("Log entry added.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.log", channel=chanurl(chan(channel))))


@bp.route("/<channel>/log/del", methods=["POST"])
@login_required
def log_del(channel):
    command = request.form.get("command", "").strip()
    method  = request.form.get("method", "").strip()
    status  = request.form.get("status", "").strip()
    cmd = f"LOG {chan(channel)} {command} {method}"
    if status:
        cmd += f" {status}"
    try:
        rpc("anope.command", g.account, "ChanServ", cmd)
        flash("Log entry removed.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.log", channel=chanurl(chan(channel))))


# ── Invite ────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/invite", methods=["POST"])
@login_required
def invite(channel):
    nick = request.form.get("nick", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"INVITE {chan(channel)} {nick}")
        flash(f"Invited {nick} to {chan(channel)}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.modes", channel=chanurl(chan(channel))))


# ── Unban ─────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/unban", methods=["POST"])
@login_required
def unban(channel):
    mask = request.form.get("mask", g.account).strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"UNBAN {chan(channel)} {mask}")
        flash(f"Unbanned {mask} from {chan(channel)}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.modes", channel=chanurl(chan(channel))))


# ── Down / Up ─────────────────────────────────────────────────────────────────

@bp.route("/<channel>/down", methods=["POST"])
@login_required
def down(channel):
    nick = request.form.get("nick", "").strip()
    cmd = f"DOWN {chan(channel)}" + (f" {nick}" if nick else "")
    try:
        rpc("anope.command", g.account, "ChanServ", cmd)
        flash("Status removed.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.modes", channel=chanurl(chan(channel))))


@bp.route("/<channel>/up", methods=["POST"])
@login_required
def up(channel):
    nick = request.form.get("nick", "").strip()
    cmd = f"UP {chan(channel)}" + (f" {nick}" if nick else "")
    try:
        rpc("anope.command", g.account, "ChanServ", cmd)
        flash("Status updated.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.modes", channel=chanurl(chan(channel))))


# ── Kick ──────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/kick", methods=["POST"])
@login_required
def kick(channel):
    nick   = request.form.get("nick", "").strip()
    reason = request.form.get("reason", "").strip()
    cmd = f"KICK {chan(channel)} {nick}"
    if reason:
        cmd += f" {reason}"
    try:
        rpc("anope.command", g.account, "ChanServ", cmd)
        flash(f"Kicked {nick}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.modes", channel=chanurl(chan(channel))))


# ── Suspend / Unsuspend (oper) ────────────────────────────────────────────────

@bp.route("/<channel>/suspend", methods=["POST"])
@login_required
def suspend(channel):
    reason = request.form.get("reason", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"SUSPEND {chan(channel)} {reason}")
        flash(f"{chan(channel)} suspended.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.set_options", channel=chanurl(chan(channel))))


@bp.route("/<channel>/unsuspend", methods=["POST"])
@login_required
def unsuspend(channel):
    try:
        rpc("anope.command", g.account, "ChanServ", f"UNSUSPEND {chan(channel)}")
        flash(f"{chan(channel)} unsuspended.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.set_options", channel=chanurl(chan(channel))))


# ── Drop ──────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/drop", methods=["GET", "POST"])
@login_required
def drop(channel):
    if request.method == "POST":
        confirm = request.form.get("confirm", "").strip()
        if confirm != chan(channel):
            flash("Channel name did not match. Drop cancelled.", "error")
            return redirect(url_for("chanserv.drop", channel=chanurl(chan(channel))))
        try:
            # Step 1: get the confirmation code
            result = rpc("anope.command", g.account, "ChanServ", f"DROP {chan(channel)}")
            code = parse_drop_code(result)
            if not code:
                flash("Could not get drop confirmation code.", "error")
                return redirect(url_for("chanserv.drop", channel=chanurl(chan(channel))))
            # Step 2: confirm with code
            rpc("anope.command", g.account, "ChanServ", f"DROP {chan(channel)} {code}")
            flash(f"{chan(channel)} has been dropped.", "success")
            return redirect(url_for("chanserv.index"))
        except AnopeError as e:
            flash(e.message, "error")
    return render_template("chanserv/drop.html", channel=chan(channel))


# ── GETKEY ────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/getkey", methods=["POST"])
@login_required
def getkey(channel):
    from utils import parse_getkey
    key = None
    try:
        result = rpc("anope.command", g.account, "ChanServ", f"GETKEY {chan(channel)}")
        key = parse_getkey(result)
        if key is None:
            flash("No key set or access denied.", "error")
    except AnopeError as e:
        flash(e.message, "error")
    try:
        ci = rpc("anope.channel", chan(channel))
    except AnopeError:
        ci = None
    return _modes_render(channel, ci, key=key)


# ── STATUS ────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/status", methods=["POST"])
@login_required
def status(channel):
    from utils import parse_status
    nick = request.form.get("nick", g.account).strip()
    status_result = None
    try:
        result = rpc("anope.command", g.account, "ChanServ", f"STATUS {chan(channel)} {nick}")
        status_result = parse_status(result)
    except AnopeError as e:
        flash(e.message, "error")
    try:
        ci = rpc("anope.channel", chan(channel))
    except AnopeError:
        ci = None
    return _modes_render(channel, ci, status_result=status_result)


# ── TOPIC ─────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/topic", methods=["POST"])
@login_required
def topic(channel):
    text = request.form.get("topic", "").strip()
    cmd = f"TOPIC {chan(channel)}"
    if text:
        cmd += f" {text}"
    try:
        rpc("anope.command", g.account, "ChanServ", cmd)
        flash("Topic updated.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.modes", channel=chanurl(chan(channel))))


# ── MODE ──────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/mode", methods=["POST"])
@login_required
def mode(channel):
    modes = request.form.get("modes", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"MODE {chan(channel)} {modes}")
        flash(f"Mode {modes} set.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.modes", channel=chanurl(chan(channel))))


# ── BAN ───────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/ban", methods=["POST"])
@login_required
def ban(channel):
    mask   = request.form.get("mask", "").strip()
    expiry = request.form.get("expiry", "").strip()
    reason = request.form.get("reason", "").strip()
    prefix = f"+{expiry} " if expiry else ""
    cmd = f"BAN {chan(channel)} {prefix}{mask}"
    if reason:
        cmd += f" {reason}"
    try:
        rpc("anope.command", g.account, "ChanServ", cmd)
        flash(f"Banned {mask}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.modes", channel=chanurl(chan(channel))))


# ── SYNC ──────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/sync", methods=["POST"])
@login_required
def sync(channel):
    try:
        rpc("anope.command", g.account, "ChanServ", f"SYNC {chan(channel)}")
        flash(f"{chan(channel)} synced.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.modes", channel=chanurl(chan(channel))))


# ── ENFORCE ───────────────────────────────────────────────────────────────────

@bp.route("/<channel>/enforce", methods=["POST"])
@login_required
def enforce(channel):
    what = request.form.get("what", "").strip()
    cmd = f"ENFORCE {chan(channel)}"
    if what:
        cmd += f" {what}"
    try:
        result = rpc("anope.command", g.account, "ChanServ", cmd)
        flash(" ".join(result) if result else "Enforced.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.modes", channel=chanurl(chan(channel))))


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
        return redirect(url_for("chanserv.modes", channel=chanurl(chan(channel))))
    try:
        rpc("anope.command", g.account, "ChanServ", f"{cmd} {chan(channel)} {nick}")
        action = "given to" if not cmd.startswith("DE") else "taken from"
        flash(f"{cmd} {action} {nick}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.modes", channel=chanurl(chan(channel))))


# ── STATS ─────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/stats")
@login_required
def stats(channel):
    from utils import parse_stats
    my_stats = None
    try:
        result = rpc("anope.command", g.account, "ChanServ", f"STATS {chan(channel)}")
        my_stats = parse_stats(result)
    except AnopeError as e:
        flash(e.message, "error")
    try:
        ci = _channel_info(channel)
        chanstats_on = "chanstats" in ci.get("option_set", set())
    except AnopeError:
        chanstats_on = False
    return render_template("chanserv/stats.html", channel=chan(channel), stats=my_stats, chanstats_on=chanstats_on)


@bp.route("/<channel>/set/chanstats", methods=["POST"])
@login_required
def set_chanstats(channel):
    state = request.form.get("state", "OFF").upper()
    try:
        rpc("anope.command", g.account, "ChanServ", f"SET CHANSTATS {chan(channel)} {state}")
        flash(f"Chanstats {state.lower()} for {chan(channel)}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.stats", channel=chanurl(chan(channel))))


@bp.route("/<channel>/top")
@login_required
def top(channel):
    from utils import parse_cs_top
    entries = []
    try:
        result = rpc("anope.command", g.account, "ChanServ", f"TOP10 {chan(channel)}")
        entries = parse_cs_top(result)
    except AnopeError as e:
        flash(e.message, "error")
    return render_template("chanserv/top.html", channel=chan(channel), entries=entries, scope="channel")


@bp.route("/gstats")
@login_required
def gstats():
    from utils import parse_stats
    my_stats = None
    try:
        result = rpc("anope.command", g.account, "ChanServ", f"GSTATS {g.account}")
        my_stats = parse_stats(result)
    except AnopeError as e:
        flash(e.message, "error")
    return render_template("chanserv/gstats.html", stats=my_stats)


@bp.route("/gtop")
@login_required
def gtop():
    from utils import parse_cs_top
    entries = []
    try:
        result = rpc("anope.command", g.account, "ChanServ", "GTOP10")
        entries = parse_cs_top(result)
    except AnopeError as e:
        flash(e.message, "error")
    return render_template("chanserv/top.html", channel=None, entries=entries, scope="network")


# ── CLONE ─────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/clone", methods=["GET", "POST"])
@login_required
def clone(channel):
    from utils import parse_clone_result
    result = None
    if request.method == "POST":
        target = request.form.get("target", "").strip()
        what   = request.form.get("what", "").strip()
        cmd = f"CLONE {chan(channel)} {target}"
        if what:
            cmd += f" {what}"
        try:
            lines = rpc("anope.command", g.account, "ChanServ", cmd)
            result = parse_clone_result(lines)
            flash("Clone completed.", "success")
        except AnopeError as e:
            flash(e.message, "error")
    return render_template("chanserv/clone.html", channel=chan(channel), result=result)


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


# ── ACCESS (numeric) ──────────────────────────────────────────────────────────

@bp.route("/<channel>/access_num")
@login_required
def access_num(channel):
    from utils import parse_access_list
    try:
        result = rpc("anope.command", g.account, "ChanServ", f"ACCESS {chan(channel)} LIST * ALL")
        entries = parse_access_list(result)
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    return render_template("chanserv/access_num.html", channel=chan(channel), entries=entries)


@bp.route("/<channel>/access_num/add", methods=["POST"])
@login_required
def access_num_add(channel):
    mask  = request.form.get("mask", "").strip()
    level = request.form.get("level", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"ACCESS {chan(channel)} ADD {mask} {level}")
        flash(f"Added {mask} at level {level}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.access_num", channel=chanurl(chan(channel))))


@bp.route("/<channel>/access_num/del", methods=["POST"])
@login_required
def access_num_del(channel):
    mask = request.form.get("mask", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"ACCESS {chan(channel)} DEL {mask}")
        flash(f"Removed {mask}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.access_num", channel=chanurl(chan(channel))))


# ── xOP ───────────────────────────────────────────────────────────────────────

XOP_TYPES = ["VOP", "HOP", "AOP", "SOP", "QOP"]


@bp.route("/<channel>/xop")
@login_required
def xop(channel):
    from utils import parse_xop_list
    lists = {}
    for xtype in XOP_TYPES:
        try:
            result = rpc("anope.command", g.account, "ChanServ", f"{xtype} {chan(channel)} LIST")
            lists[xtype] = parse_xop_list(result)
        except AnopeError:
            lists[xtype] = []
    return render_template("chanserv/xop.html", channel=chan(channel), lists=lists, xop_types=XOP_TYPES)


@bp.route("/<channel>/xop/add", methods=["POST"])
@login_required
def xop_add(channel):
    xtype = request.form.get("type", "").strip().upper()
    mask  = request.form.get("mask", "").strip()
    if xtype not in XOP_TYPES:
        flash("Invalid xOP type.", "error")
        return redirect(url_for("chanserv.xop", channel=chanurl(chan(channel))))
    try:
        rpc("anope.command", g.account, "ChanServ", f"{xtype} {chan(channel)} ADD {mask}")
        flash(f"Added {mask} to {xtype}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.xop", channel=chanurl(chan(channel))))


@bp.route("/<channel>/xop/del", methods=["POST"])
@login_required
def xop_del(channel):
    xtype = request.form.get("type", "").strip().upper()
    mask  = request.form.get("mask", "").strip()
    if xtype not in XOP_TYPES:
        flash("Invalid xOP type.", "error")
        return redirect(url_for("chanserv.xop", channel=chanurl(chan(channel))))
    try:
        rpc("anope.command", g.account, "ChanServ", f"{xtype} {chan(channel)} DEL {mask}")
        flash(f"Removed {mask} from {xtype}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.xop", channel=chanurl(chan(channel))))


# ── LEVELS ────────────────────────────────────────────────────────────────────

@bp.route("/<channel>/levels")
@login_required
def levels(channel):
    from utils import parse_levels_list
    try:
        result = rpc("anope.command", g.account, "ChanServ", f"LEVELS {chan(channel)} LIST")
        entries = parse_levels_list(result)
    except AnopeError as e:
        flash(e.message, "error")
        entries = []
    return render_template("chanserv/levels.html", channel=chan(channel), entries=entries)


@bp.route("/<channel>/levels/set", methods=["POST"])
@login_required
def levels_set(channel):
    privilege = request.form.get("privilege", "").strip().upper()
    level     = request.form.get("level", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"LEVELS {chan(channel)} SET {privilege} {level}")
        flash(f"{privilege} set to {level}.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.levels", channel=chanurl(chan(channel))))


@bp.route("/<channel>/levels/reset", methods=["POST"])
@login_required
def levels_reset(channel):
    privilege = request.form.get("privilege", "").strip().upper()
    try:
        rpc("anope.command", g.account, "ChanServ", f"LEVELS {chan(channel)} RESET {privilege}")
        flash(f"{privilege} reset to default.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.levels", channel=chanurl(chan(channel))))


@bp.route("/<channel>/levels/reset_all", methods=["POST"])
@login_required
def levels_reset_all(channel):
    try:
        rpc("anope.command", g.account, "ChanServ", f"LEVELS {chan(channel)} RESET")
        flash("All levels reset to defaults.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.levels", channel=chanurl(chan(channel))))
