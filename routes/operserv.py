from flask import Blueprint, render_template, request, flash, redirect, url_for, g
from rpc import rpc, AnopeError
from auth import login_required
from utils import parse_akill_view

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


@bp.route("/sessions")
@login_required
@oper_required
def sessions():
    try:
        result = rpc("anope.command", g.account, "OperServ", "SESSION LIST 1")
    except AnopeError as e:
        flash(e.message, "error")
        result = []
    return render_template("operserv/sessions.html", result=result)


@bp.route("/news")
@login_required
@oper_required
def news():
    try:
        result = rpc("anope.command", g.account, "OperServ", "NEWS LIST")
    except AnopeError as e:
        flash(e.message, "error")
        result = []
    return render_template("operserv/news.html", result=result)
