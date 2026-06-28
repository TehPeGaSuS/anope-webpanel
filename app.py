import os
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, redirect, url_for, render_template, session, g
from rpc import rpc, AnopeError


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")

    app.config["ANOPE_RPC_URL"] = os.environ.get("ANOPE_RPC_URL", "http://127.0.0.1:8080/jsonrpc")
    app.config["ANOPE_RPC_TOKEN"] = os.environ.get("ANOPE_RPC_TOKEN", "")

    # ---------- Template filters ----------
    @app.template_filter("chanurl")
    def chanurl_filter(channel):
        """Strip leading # for use in url_for channel arguments."""
        return channel.lstrip("#") if channel else channel

    # ---------- Network branding ----------
    @app.context_processor
    def inject_network():
        return {
            "network_name":  os.environ.get("NETWORK_NAME", "Anope"),
            "network_url":   os.environ.get("NETWORK_URL", "/"),
            "network_logo":  os.environ.get("NETWORK_LOGO", ""),
            "network_color": os.environ.get("NETWORK_COLOR", "#1f6feb"),
        }

    # ---------- Template filters ----------
    @app.template_filter("datetimeformat")
    def datetimeformat(ts):
        if not ts:
            return "—"
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        except (ValueError, TypeError):
            return str(ts)

    # ---------- Blueprints ----------
    from auth import bp as auth_bp
    from routes.nickserv import bp as ns_bp
    from routes.chanserv import bp as cs_bp
    from routes.services import memo_bp, host_bp
    from routes.operserv import bp as os_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(ns_bp)
    app.register_blueprint(cs_bp)
    app.register_blueprint(memo_bp)
    app.register_blueprint(host_bp)
    app.register_blueprint(os_bp)

    # ---------- Dashboard ----------
    @app.route("/")
    def index():
        if "account" not in session:
            return redirect(url_for("auth.login"))
        return redirect(url_for("dashboard"))

    @app.route("/dashboard")
    def dashboard():
        if "account" not in session:
            return redirect(url_for("auth.login"))
        g.account = session["account"]
        try:
            users = rpc("anope.listUsers")
            channels = rpc("anope.listChannels")
            accounts = rpc("anope.listAccounts")
            # check if oper
            account = rpc("anope.account", g.account)
            is_oper = bool(account.get("opertype"))
        except AnopeError:
            users = channels = accounts = None
            is_oper = False
        return render_template(
            "dashboard.html",
            user_count=len(users) if users else "?",
            channel_count=len(channels) if channels else "?",
            account_count=len(accounts) if accounts else "?",
            is_oper=is_oper,
        )

    # ---------- Error handlers ----------
    @app.errorhandler(404)
    def not_found(e):
        return "404 Not Found", 404

    @app.errorhandler(500)
    def server_error(e):
        return "500 Internal Server Error", 500

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
        host=os.environ.get("BIND", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5000)),
    )
