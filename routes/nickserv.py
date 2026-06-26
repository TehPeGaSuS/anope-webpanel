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


@bp.route("/confirm", methods=["GET", "POST"])
@login_required
def confirm():
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        try:
            rpc("anope.command", g.account, "NickServ", f"CONFIRM {code}")
            flash("Email confirmed successfully.", "success")
            return redirect(url_for("nickserv.info"))
        except AnopeError as e:
            flash(e.message, "error")
    return render_template("nickserv/confirm.html")


@bp.route("/confirm/<code>")
def confirm_link(code):
    # Unauthenticated — token from email link
    try:
        rpc("anope.command", None, "NickServ", f"CONFIRM {code}")
        flash("Email confirmed. You can now log in.", "success")
    except AnopeError as e:
        flash(e.message, "error")
    return redirect(url_for("auth.login"))


@bp.route("/reset", methods=["GET", "POST"])
def reset():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        try:
            rpc("anope.command", username, "NickServ", "RESETPASS")
            flash("If that account exists, a reset email has been sent.", "success")
            return redirect(url_for("auth.login"))
        except AnopeError as e:
            flash(e.message, "error")
    return render_template("nickserv/reset.html")


@bp.route("/reset/<code>", methods=["GET", "POST"])
def reset_confirm(code):
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        try:
            rpc("anope.command", username, "NickServ", f"CONFIRM {code} {password}")
            flash("Password reset successfully. You can now log in.", "success")
            return redirect(url_for("auth.login"))
        except AnopeError as e:
            flash(e.message, "error")
    return render_template("nickserv/reset_confirm.html", code=code)


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
