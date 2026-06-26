from flask import Blueprint, render_template, request, flash, redirect, url_for, g
from rpc import rpc, AnopeError
from auth import login_required
from utils import parse_alist, parse_flags_list, parse_akick_view

bp = Blueprint("chanserv", __name__, url_prefix="/chanserv")


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
    mask = request.form.get("mask", "").strip()
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
    mask = request.form.get("mask", "").strip()
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
        flash(f"Removed {mask} from akick list.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.akick", channel=channel))


@bp.route("/<channel>/modes")
@login_required
def modes(channel):
    try:
        ci = rpc("anope.channel", channel)
    except AnopeError as e:
        flash(e.message, "error")
        ci = None
    return render_template("chanserv/modes.html", channel=channel, ci=ci)


@bp.route("/<channel>/set")
@login_required
def set_options(channel):
    return render_template("chanserv/set.html", channel=channel)


@bp.route("/<channel>/set", methods=["POST"])
@login_required
def set_options_save(channel):
    option = request.form.get("option", "").strip()
    value = request.form.get("value", "").strip()
    try:
        rpc("anope.command", g.account, "ChanServ", f"SET {channel} {option} {value}")
        flash("Channel setting updated.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("chanserv.set_options", channel=channel))


@bp.route("/<channel>/drop", methods=["GET", "POST"])
@login_required
def drop(channel):
    if request.method == "POST":
        confirm = request.form.get("confirm", "").strip()
        if confirm != channel:
            flash("Channel name did not match. Drop cancelled.", "error")
            return redirect(url_for("chanserv.drop", channel=channel))
        try:
            rpc("anope.command", g.account, "ChanServ", f"DROP {channel}")
            flash(f"{channel} has been dropped.", "success")
            return redirect(url_for("chanserv.index"))
        except AnopeError as e:
            flash(e.message, "error")
    return render_template("chanserv/drop.html", channel=channel)
