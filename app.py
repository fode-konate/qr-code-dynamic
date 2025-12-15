from flask import (
    Flask, redirect, request, render_template, send_file, url_for,
    flash, send_from_directory, session
)
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import text
import qrcode
import io
import os
import json
import uuid
from werkzeug.utils import secure_filename

# -------------------------
# Flask config
# -------------------------
app = Flask(__name__)
app.secret_key = "supersecretkey"
app.config["UPLOAD_FOLDER"] = "files"

db_url = os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db = SQLAlchemy(app)

# -------------------------
# Model
# -------------------------
class URL(db.Model):
    id = db.Column(db.String(8), primary_key=True)
    custom_id = db.Column(db.String(100), unique=True, nullable=True)
    target_url = db.Column(db.Text, nullable=False)

    mode = db.Column(db.String(20), default="redirect")  # redirect | landing

    folder = db.Column(db.String(100), default="Général")
    filename = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    deleted = db.Column(db.Boolean, default=False)

    # ---- Landing (page modifiable) ----
    brand = db.Column(db.String(120), default="HDCA")
    page_title = db.Column(db.String(200), default="HDCA")
    header_title = db.Column(db.String(200), default="")

    # Ligne "fixe" (tableau)
    armoire = db.Column(db.String(200), default="Armoire Ventilation")
    chantier = db.Column(db.String(200), default="")
    client = db.Column(db.String(200), default="")
    ville = db.Column(db.String(200), default="")
    adresse = db.Column(db.String(200), default="")

    # Le reste modifiable
    section_title = db.Column(db.String(200), default="Documents:")
    footer_text = db.Column(db.String(400), default="")
    phone1 = db.Column(db.String(50), default="")
    phone2 = db.Column(db.String(50), default="")
    email = db.Column(db.String(120), default="")

    # Liste des docs: [{"nom":"...", "url":"..."}]
    documents_json = db.Column(db.Text, default="[]")


# -------------------------
# Auto-migration schema (Render free friendly)
# -------------------------
def ensure_schema():
    db.create_all()
    try:
        # base
        db.session.execute(text("ALTER TABLE url ADD COLUMN IF NOT EXISTS mode VARCHAR(20) DEFAULT 'redirect'"))
        db.session.execute(text("ALTER TABLE url ADD COLUMN IF NOT EXISTS folder VARCHAR(100) DEFAULT 'Général'"))
        db.session.execute(text("ALTER TABLE url ADD COLUMN IF NOT EXISTS filename VARCHAR(200)"))
        db.session.execute(text("ALTER TABLE url ADD COLUMN IF NOT EXISTS created_at TIMESTAMP"))
        db.session.execute(text("ALTER TABLE url ADD COLUMN IF NOT EXISTS deleted BOOLEAN DEFAULT FALSE"))

        # landing
        db.session.execute(text("ALTER TABLE url ADD COLUMN IF NOT EXISTS brand VARCHAR(120) DEFAULT 'HDCA'"))
        db.session.execute(text("ALTER TABLE url ADD COLUMN IF NOT EXISTS page_title VARCHAR(200) DEFAULT 'HDCA'"))
        db.session.execute(text("ALTER TABLE url ADD COLUMN IF NOT EXISTS header_title VARCHAR(200) DEFAULT ''"))

        db.session.execute(text("ALTER TABLE url ADD COLUMN IF NOT EXISTS armoire VARCHAR(200) DEFAULT 'Armoire Ventilation'"))
        db.session.execute(text("ALTER TABLE url ADD COLUMN IF NOT EXISTS chantier VARCHAR(200) DEFAULT ''"))
        db.session.execute(text("ALTER TABLE url ADD COLUMN IF NOT EXISTS client VARCHAR(200) DEFAULT ''"))
        db.session.execute(text("ALTER TABLE url ADD COLUMN IF NOT EXISTS ville VARCHAR(200) DEFAULT ''"))
        db.session.execute(text("ALTER TABLE url ADD COLUMN IF NOT EXISTS adresse VARCHAR(200) DEFAULT ''"))

        db.session.execute(text("ALTER TABLE url ADD COLUMN IF NOT EXISTS section_title VARCHAR(200) DEFAULT 'Documents:'"))
        db.session.execute(text("ALTER TABLE url ADD COLUMN IF NOT EXISTS footer_text VARCHAR(400) DEFAULT ''"))

        db.session.execute(text("ALTER TABLE url ADD COLUMN IF NOT EXISTS phone1 VARCHAR(50) DEFAULT ''"))
        db.session.execute(text("ALTER TABLE url ADD COLUMN IF NOT EXISTS phone2 VARCHAR(50) DEFAULT ''"))
        db.session.execute(text("ALTER TABLE url ADD COLUMN IF NOT EXISTS email VARCHAR(120) DEFAULT ''"))

        db.session.execute(text("ALTER TABLE url ADD COLUMN IF NOT EXISTS documents_json TEXT DEFAULT '[]'"))

        # normalisation
        db.session.execute(text("UPDATE url SET mode='redirect' WHERE mode IS NULL"))
        db.session.execute(text("UPDATE url SET documents_json='[]' WHERE documents_json IS NULL"))
        db.session.execute(text("UPDATE url SET deleted=FALSE WHERE deleted IS NULL"))

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print("Schema update warning:", e)


with app.app_context():
    ensure_schema()


# -------------------------
# Auth middleware
# Public: /redirect/* and /pdf/* are accessible without login (scan)
# Admin: everything else requires login
# -------------------------
@app.before_request
def require_login():
    allowed_paths = ["/login"]
    if request.path.startswith("/redirect/") or request.path.startswith("/pdf/"):
        return
    if not session.get("authenticated") and request.path not in allowed_paths:
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == "So!t3chGC":
            session["authenticated"] = True
            return redirect(url_for("home"))
        flash("Mot de passe incorrect.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Déconnecté avec succès.", "info")
    return redirect(url_for("login"))


# -------------------------
# Pages
# -------------------------
@app.route("/")
def home():
    return render_template("index.html")


# -------------------------
# Generate QR (dynamic)
# -------------------------
@app.route("/generate", methods=["POST"])
def generate():
    target_url = request.form["target_url"]
    fill_color = request.form["fill_color"]
    back_color = request.form["back_color"]
    folder = request.form.get("folder", "Général")
    custom_id = request.form.get("custom_id") or str(uuid.uuid4())[:8]
    mode = request.form.get("mode", "redirect")  # "landing" if checkbox checked

    if URL.query.filter_by(custom_id=custom_id).first():
        flash("Cet identifiant est déjà utilisé.", "danger")
        return redirect(url_for("home"))

    unique_id = str(uuid.uuid4())[:8]
    dynamic_url = request.host_url + "redirect/" + unique_id

    # Valeurs landing par défaut si mode=landing
    documents = [{"nom": "Document 1", "url": target_url}] if mode == "landing" else []

    url = URL(
        id=unique_id,
        custom_id=custom_id,
        target_url=target_url,
        folder=folder,
        mode=mode,
        documents_json=json.dumps(documents, ensure_ascii=False),
        header_title=custom_id if mode == "landing" else ""
    )

    db.session.add(url)
    db.session.commit()

    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(dynamic_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fill_color, back_color=back_color)

    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)

    flash(f"QR Code créé pour l’identifiant : {custom_id}", "success")
    return send_file(buf, mimetype="image/png", as_attachment=True, download_name="qr_code.png")


# -------------------------
# Public redirect (scan)
# -------------------------
@app.route("/redirect/<unique_id>")
def redirect_dynamic(unique_id):
    url = URL.query.filter_by(id=unique_id, deleted=False).first()
    if not url:
        return "Lien invalide ou supprimé.", 404

    if url.mode == "redirect":
        return redirect(url.target_url)

    if url.mode == "landing":
        try:
            documents = json.loads(url.documents_json or "[]")
        except Exception:
            documents = []

        armoire = {
            "nom": url.header_title or (url.custom_id or "Fiche"),
            "armoire": url.armoire,
            "chantier": url.chantier,
            "client": url.client,
            "ville": url.ville,
            "adresse": url.adresse,
        }

        return render_template(
            "landing.html",
            brand=url.brand or "HDCA",
            page_title=url.page_title or "HDCA",
            section_title=url.section_title or "Documents:",
            footer_text=url.footer_text or "",
            armoire=armoire,
            documents=documents,
            phone1=url.phone1 or "",
            phone2=url.phone2 or "",
            email=url.email or "",
        )

    return "Mode invalide", 400


# -------------------------
# Upload PDF (optional local)
# -------------------------
@app.route("/upload", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        file = request.files.get("file")
        folder = request.form.get("folder", "Général")
        custom_id = request.form.get("custom_id") or str(uuid.uuid4())[:8]
        mode = request.form.get("mode", "redirect")

        if not file or file.filename == "":
            flash("Aucun fichier sélectionné.", "danger")
            return redirect(request.url)

        if URL.query.filter_by(custom_id=custom_id).first():
            flash("Cet identifiant est déjà utilisé.", "danger")
            return redirect(request.url)

        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(file_path)

        unique_id = str(uuid.uuid4())[:8]
        file_url = url_for("download_pdf", filename=filename, _external=True)

        documents = [{"nom": filename, "url": file_url}] if mode == "landing" else []

        new_url = URL(
            id=unique_id,
            custom_id=custom_id,
            target_url=file_url,
            folder=folder,
            filename=filename,
            mode=mode,
            documents_json=json.dumps(documents, ensure_ascii=False),
            header_title=custom_id if mode == "landing" else ""
        )

        db.session.add(new_url)
        db.session.commit()

        qr = qrcode.make(request.host_url + "redirect/" + unique_id)
        buf = io.BytesIO()
        qr.save(buf, format="PNG")
        buf.seek(0)

        flash(f"PDF uploadé et QR Code généré (ID : {custom_id})", "success")
        return send_file(buf, mimetype="image/png", as_attachment=True, download_name="qr_code.png")

    return render_template("upload.html")


@app.route("/pdf/<filename>")
def download_pdf(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# -------------------------
# Admin: edit landing (protected by middleware)
# -------------------------
@app.route("/landing/edit/<unique_id>", methods=["GET", "POST"])
def edit_landing(unique_id):
    url = URL.query.filter_by(id=unique_id, deleted=False).first()
    if not url:
        return "QR Code non trouvé.", 404

    if request.method == "POST":
        # tableau fixe
        url.armoire = request.form.get("armoire", "")
        url.chantier = request.form.get("chantier", "")
        url.client = request.form.get("client", "")
        url.ville = request.form.get("ville", "")
        url.adresse = request.form.get("adresse", "")

        # modifiables
        url.brand = request.form.get("brand", "HDCA")
        url.page_title = request.form.get("page_title", "HDCA")
        url.header_title = request.form.get("header_title", "")

        url.section_title = request.form.get("section_title", "Documents:")
        url.footer_text = request.form.get("footer_text", "")

        url.phone1 = request.form.get("phone1", "")
        url.phone2 = request.form.get("phone2", "")
        url.email = request.form.get("email", "")

        # documents
        noms = request.form.getlist("doc_name[]")
        links = request.form.getlist("doc_url[]")
        docs = []
        for n, u in zip(noms, links):
            n = (n or "").strip()
            u = (u or "").strip()
            if n and u:
                docs.append({"nom": n, "url": u})
        url.documents_json = json.dumps(docs, ensure_ascii=False)

        db.session.commit()
        flash("Landing mise à jour ✅", "success")
        return redirect(url_for("list_qr"))

    try:
        documents = json.loads(url.documents_json or "[]")
    except Exception:
        documents = []

    return render_template("edit_landing.html", item=url, documents=documents)


# -------------------------
# Update QR target (admin)
# -------------------------
@app.route("/update/<unique_id>", methods=["GET", "POST"])
def update(unique_id):
    url = URL.query.filter_by(id=unique_id).first()
    if not url:
        return "QR Code non trouvé.", 404

    if request.method == "POST":
        url.target_url = request.form["new_url"]
        url.folder = request.form.get("folder", "Général")
        file = request.files.get("file")

        if file and file.filename:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            url.target_url = url_for("download_pdf", filename=filename, _external=True)
            url.filename = filename

        db.session.commit()
        flash("QR Code mis à jour avec succès.", "success")
        return redirect(url_for("list_qr"))

    return render_template("update.html", unique_id=unique_id, target_url=url.target_url, folder=url.folder)


# -------------------------
# List (admin)
# -------------------------
@app.route("/list")
def list_qr():
    folder = request.args.get("folder")
    if folder:
        urls = URL.query.filter_by(folder=folder, deleted=False).all()
    else:
        urls = URL.query.filter_by(deleted=False).all()

    folders = [f.folder for f in URL.query.with_entities(URL.folder).distinct()]
    return render_template("list.html", qr_codes=urls, folders=folders, selected_folder=folder)


@app.route("/delete/<unique_id>", methods=["POST"])
def delete(unique_id):
    url = URL.query.filter_by(id=unique_id).first()
    if url:
        url.deleted = True
        db.session.commit()
        flash("QR Code déplacé dans la corbeille.", "success")
    return redirect(url_for("list_qr"))


if __name__ == "__main__":
    app.run(debug=True)
