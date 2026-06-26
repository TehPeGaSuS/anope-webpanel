from functools import wraps
from flask import (
    Blueprint, request, session, redirect, url_for,
    render_template, flash, g
)
from rpc import rpc, AnopeError

bp = Blueprint("auth", __name__)


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "account" not in session:
            return redirect(url_for("auth.login", next=request.path))
        g.account = session["account"]
        return f(*args, **kwargs)
    return wrapper


@bp.route("/login", methods=["GET", "POST"])
def login():
    if "account" in session:
        return redirect(url_for("nickserv.info"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required.", "error")
            return render_template("login.html")

        try:
            result = rpc("anope.checkCredentials", username, password)
            session["account"] = result["account"]
            session["uniqueid"] = result["uniqueid"]
            # cache oper status in session to avoid extra RPC on every page
            try:
                from rpc import rpc as _rpc
                acct = _rpc("anope.account", result["account"])
                session["is_oper"] = bool(acct.get("opertype"))
            except Exception:
                session["is_oper"] = False
            next_url = request.form.get("next") or url_for("nickserv.info")
            return redirect(next_url)
        except AnopeError as e:
            flash(e.message, "error")

    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
