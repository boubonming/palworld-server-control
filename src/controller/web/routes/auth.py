"""Authentication and health endpoints."""

from flask import flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from core import config_manager


def register_auth_routes(app):
    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            password_hash = config_manager.CONFIG.get("web_password_hash", "")
            supplied_password = request.form.get("password", "")
            if password_hash and check_password_hash(password_hash, supplied_password):
                session.clear()
                session["authenticated"] = True
                next_path = request.args.get("next", "")
                destination = (
                    next_path
                    if next_path.startswith("/") and not next_path.startswith("//")
                    else url_for("dashboard")
                )
                return redirect(destination)
            flash("Incorrect password.", "error")
        return render_template("login.html")

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))
