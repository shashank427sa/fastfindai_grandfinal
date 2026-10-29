        flash(
            "Claim decision saved. Please arrange a safe handover in person.",
            "success",
        )

    return redirect(url_for("claims_page"))


@app.route("/admin")
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        abort(403)

    items = Item.query.order_by(Item.created_at.desc()).limit(200).all()
    claims = Claim.query.order_by(Claim.created_at.desc()).limit(200).all()
    users = User.query.order_by(User.id.desc()).limit(200).all()
    return render_template("admin.html", items=items, claims=claims, users=users)


@app.route("/admin/claim/<int:claim_id>/<decision>", methods=["POST"])
@login_required
def admin_decide_claim(claim_id, decision):
    if not current_user.is_admin:
        abort(403)
    if decision not in {"approve", "reject"}:
        abort(404)

    claim_obj = db.session.get(Claim, claim_id)
    if not claim_obj:
        abort(404)

    if claim_obj.status == "pending":
        claim_obj.status = "approved" if decision == "approve" else "rejected"
        match = db.session.get(Match, claim_obj.match_id)
        if match and decision == "approve":
            match.status = "claim-approved"
        db.session.commit()
        flash(
            "Admin review saved. Arrange a safe handover; this is not proof of identity.",
            "success",
        )
    else:
        flash("This claim has already been reviewed.", "error")

    return redirect(url_for("admin_dashboard"))


@app.route("/private-image/<int:item_id>")
@login_required
def private_image(item_id):
    item = db.session.get(Item, item_id)
    if not item:
        abort(404)

    allowed = item.owner_id == current_user.id
    if not allowed:
        related = Match.query.filter(
            (Match.lost_id == item_id) | (Match.found_id == item_id)
        ).all()
        allowed = any(is_match_member(match) for match in related)

    if not allowed or not item.image_filename:
        abort(404)

    path = UPLOAD_DIR / item.image_filename
    if not path.exists():
        abort(404)

    return send_file(path)


@app.errorhandler(413)
def too_large(_error):
    return "Image too large. Maximum upload size is 5 MB.", 413


def initialize_database():
    """Create tables and safely add the role column to older SQLite databases."""
    db.create_all()

    inspector = inspect(db.engine)
    user_columns = {column["name"] for column in inspector.get_columns("user")}

    # db.create_all() does not alter existing tables. Add this column when
    # upgrading a database created by the earlier version of this application.
    if "role" not in user_columns:
        with db.engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE user ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'")
            )

    admin_email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    if admin_email:
        admin_user = User.query.filter_by(email=admin_email).first()
        if admin_user and admin_user.role != "admin":
            admin_user.role = "admin"
            db.session.commit()


with app.app_context():
    initialize_database()


if __name__ == "__main__":
    # For local development only. Render uses the Gunicorn start command.
    app.run(debug=os.environ.get("FLASK_DEBUG", "").lower() == "true")