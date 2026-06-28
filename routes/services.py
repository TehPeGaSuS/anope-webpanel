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
    return render_template("memoserv/index.html", memos=memos)


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


# ---------- HostServ ----------

host_bp = Blueprint("hostserv", __name__, url_prefix="/hostserv")


@host_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        vhost = request.form.get("vhost", "").strip()
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
