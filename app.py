from flask import Flask, redirect, request, render_template, send_file, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import qrcode
import io
import os
import uuid
from werkzeug.utils import secure_filename

# Configuration Flask
app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['UPLOAD_FOLDER'] = 'files'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Dossier de fichiers PDF
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialisation de SQLAlchemy
db = SQLAlchemy(app)

# Définition du modèle
class URL(db.Model):
    id = db.Column(db.String(8), primary_key=True)
    custom_id = db.Column(db.String(100), unique=True, nullable=True)
    target_url = db.Column(db.Text, nullable=False)
    folder = db.Column(db.String(100), default='Général')
    filename = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    deleted = db.Column(db.Boolean, default=False)

# Création des tables
with app.app_context():
    db.create_all()

# Page d’accueil
@app.route('/')
def home():
    return render_template('index.html')

# Génération QR code pour URL
@app.route('/generate', methods=['POST'])
def generate():
    target_url = request.form['target_url']
    fill_color = request.form['fill_color']
    back_color = request.form['back_color']
    folder = request.form.get('folder', 'Général')
    custom_id = request.form.get('custom_id') or str(uuid.uuid4())[:8]

    if URL.query.filter_by(custom_id=custom_id).first():
        flash("Cet identifiant est déjà utilisé.", "danger")
        return redirect(url_for('home'))

    unique_id = str(uuid.uuid4())[:8]
    dynamic_url = request.host_url + 'redirect/' + unique_id

    url = URL(id=unique_id, custom_id=custom_id, target_url=target_url, folder=folder)
    db.session.add(url)
    db.session.commit()

    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(dynamic_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fill_color, back_color=back_color)

    buf = io.BytesIO()
    img.save(buf, 'PNG')
    buf.seek(0)

    flash(f"QR Code créé pour l’identifiant : {custom_id}", "success")
    return send_file(buf, mimetype='image/png', as_attachment=True, download_name='qr_code.png')

# Redirection via QR code
@app.route('/redirect/<unique_id>')
def redirect_dynamic(unique_id):
    url = URL.query.filter_by(id=unique_id, deleted=False).first()
    if url:
        return redirect(url.target_url)
    return "Lien invalide ou supprimé.", 404

# Upload de fichier PDF + génération QR
@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        file = request.files.get('file')
        folder = request.form.get('folder', 'Général')
        custom_id = request.form.get('custom_id') or str(uuid.uuid4())[:8]

        if not file or file.filename == '':
            flash('Aucun fichier sélectionné.', 'danger')
            return redirect(request.url)

        if URL.query.filter_by(custom_id=custom_id).first():
            flash("Cet identifiant est déjà utilisé.", "danger")
            return redirect(request.url)

        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        unique_id = str(uuid.uuid4())[:8]
        file_url = url_for('download_pdf', filename=filename, _external=True)

        new_url = URL(id=unique_id, custom_id=custom_id, target_url=file_url, folder=folder, filename=filename)
        db.session.add(new_url)
        db.session.commit()

        qr = qrcode.make(request.host_url + 'redirect/' + unique_id)
        buf = io.BytesIO()
        qr.save(buf, format='PNG')
        buf.seek(0)

        flash(f"PDF uploadé et QR Code généré (ID : {custom_id})", "success")
        return send_file(buf, mimetype='image/png', as_attachment=True, download_name='qr_code.png')

    return render_template('upload.html')

# Téléchargement du PDF
@app.route('/pdf/<filename>')
def download_pdf(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Modification QR Code
@app.route('/update/<unique_id>', methods=['GET', 'POST'])
def update(unique_id):
    url = URL.query.filter_by(id=unique_id).first()
    if not url:
        return "QR Code non trouvé.", 404

    if request.method == 'POST':
        url.target_url = request.form['new_url']
        url.folder = request.form.get('folder', 'Général')
        file = request.files.get('file')
        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            url.target_url = url_for('download_pdf', filename=filename, _external=True)
            url.filename = filename
        db.session.commit()
        flash("QR Code mis à jour avec succès.", "success")
        return redirect(url_for('list_qr'))

    return render_template('update.html', unique_id=unique_id, target_url=url.target_url, folder=url.folder)

# Liste QR codes
@app.route('/list')
def list_qr():
    folder = request.args.get('folder')
    if folder:
        urls = URL.query.filter_by(folder=folder, deleted=False).all()
    else:
        urls = URL.query.filter_by(deleted=False).all()
    folders = [f.folder for f in URL.query.with_entities(URL.folder).distinct()]
    return render_template('list.html', qr_codes=urls, folders=folders, selected_folder=folder)

# Suppression logique
@app.route('/delete/<unique_id>', methods=['POST'])
def delete(unique_id):
    url = URL.query.filter_by(id=unique_id).first()
    if url:
        url.deleted = True
        db.session.commit()
        flash('QR Code déplacé dans la corbeille.', 'success')
    return redirect(url_for('list_qr'))

if __name__ == '__main__':
    app.run(debug=True)