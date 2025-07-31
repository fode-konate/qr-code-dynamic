from flask import Flask, redirect, request, render_template, send_file, url_for, flash, send_from_directory
import qrcode
import io
import uuid
import sqlite3
import os
import csv
from werkzeug.utils import secure_filename
from datetime import datetime

# Configuration
app = Flask(__name__)
app.secret_key = 'supersecretkey'
UPLOAD_FOLDER = 'files'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DB_PATH = 'urls.db'

# Vérifie si l'extension du fichier est autorisée (PDF)
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'

# Initialise la base de données si elle n'existe pas
def init_db():
    if not os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE urls (
                id TEXT PRIMARY KEY,
                custom_id TEXT,
                target_url TEXT,
                folder TEXT DEFAULT 'Général',
                filename TEXT,
                created_at TEXT,
                deleted INTEGER DEFAULT 0
            )
        ''')
        conn.commit()
        conn.close()

# Création de la base si besoin
init_db()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    target_url = request.form['target_url']
    folder = request.form.get('folder', 'Général')
    fill_color = request.form['fill_color']
    back_color = request.form['back_color']
    custom_id = request.form.get('custom_id', '').strip()

    unique_id = custom_id if custom_id else str(uuid.uuid4())[:8]
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO urls (id, target_url, folder, custom_id, created_at) VALUES (?, ?, ?, ?, ?)",
                  (unique_id, target_url, folder, custom_id, created_at))

    dynamic_url = request.host_url + 'redirect/' + unique_id
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(dynamic_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fill_color, back_color=back_color)
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    buf.seek(0)

    flash(f"QR Code généré avec succès (ID : {unique_id})", "success")
    return send_file(buf, mimetype='image/png', as_attachment=True, download_name='qr_code.png')

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        file = request.files.get('file')
        folder = request.form.get('folder', 'Général')
        custom_id = request.form.get('custom_id', '').strip()

        if not file or file.filename == '':
            flash('Aucun fichier sélectionné.', 'danger')
            return redirect(request.url)
        if not allowed_file(file.filename):
            flash('Seuls les fichiers PDF sont autorisés.', 'danger')
            return redirect(request.url)

        filename = secure_filename(file.filename)
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)

        unique_id = custom_id if custom_id else str(uuid.uuid4())[:8]
        file_url = url_for('download_pdf', filename=filename, _external=True)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO urls (id, target_url, folder, custom_id, filename, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                      (unique_id, file_url, folder, custom_id, filename, created_at))

        qr = qrcode.make(request.host_url + 'redirect/' + unique_id)
        buf = io.BytesIO()
        qr.save(buf, format='PNG')
        buf.seek(0)

        flash(f"PDF téléversé et QR Code généré (ID : {unique_id})", 'success')
        return send_file(buf, mimetype='image/png', as_attachment=True, download_name='qr_code.png')

    return render_template('upload.html')

@app.route('/update/<unique_id>', methods=['GET', 'POST'])
def update(unique_id):
    if request.method == 'POST':
        new_url = request.form.get('new_url')
        folder = request.form.get('folder', 'Général')
        custom_id = request.form.get('custom_id', '').strip()

        if 'file' in request.files and request.files['file'].filename:
            file = request.files['file']
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                file.save(file_path)
                new_url = url_for('download_pdf', filename=filename, _external=True)
            else:
                flash('Fichier non valide.', 'danger')
                return redirect(request.url)

        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("UPDATE urls SET target_url = ?, folder = ?, custom_id = ? WHERE id = ?",
                      (new_url, folder, custom_id, unique_id))

        flash("QR Code mis à jour avec succès.", "success")
        return redirect(url_for('list_qr'))

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT target_url, folder, custom_id FROM urls WHERE id = ?", (unique_id,))
        result = c.fetchone()

    if result:
        return render_template('update.html', unique_id=unique_id, target_url=result[0], folder=result[1], custom_id=result[2])
    else:
        return "QR Code introuvable.", 404

@app.route('/redirect/<unique_id>')
def redirect_dynamic(unique_id):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT target_url FROM urls WHERE id = ? AND deleted = 0", (unique_id,))
        row = c.fetchone()
    return redirect(row[0]) if row else "QR Code invalide ou supprimé", 404

@app.route('/list')
def list_qr():
    folder = request.args.get('folder')
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        if folder:
            c.execute("SELECT id, custom_id, target_url, folder FROM urls WHERE deleted = 0 AND folder = ?", (folder,))
        else:
            c.execute("SELECT id, custom_id, target_url, folder FROM urls WHERE deleted = 0")
        qr_codes = c.fetchall()

        c.execute("SELECT DISTINCT folder FROM urls WHERE deleted = 0")
        folders = [row[0] for row in c.fetchall()]
    return render_template('list.html', qr_codes=qr_codes, folders=folders, selected_folder=folder)

@app.route('/pdf/<filename>')
def download_pdf(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/delete/<unique_id>', methods=['POST'])
def delete(unique_id):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("UPDATE urls SET deleted = 1 WHERE id = ?", (unique_id,))
    flash("QR Code supprimé (corbeille).", "success")
    return redirect(url_for('list_qr'))

@app.route('/qr/<unique_id>')
def get_qr(unique_id):
    qr = qrcode.make(request.host_url + 'redirect/' + unique_id)
    buf = io.BytesIO()
    qr.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@app.route('/export')
def export_csv():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT id, custom_id, target_url, folder, created_at FROM urls WHERE deleted = 0")
        rows = c.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Nom', 'URL', 'Dossier', 'Date'])
    writer.writerows(rows)
    output.seek(0)

    return send_file(io.BytesIO(output.read().encode()), mimetype='text/csv', as_attachment=True, download_name='qr_codes.csv')

if __name__ == '__main__':
    app.run(debug=True)