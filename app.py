from flask import Flask, redirect, request, render_template, send_file, url_for, flash, send_from_directory
import qrcode
import io
import uuid
import sqlite3
import os
from werkzeug.utils import secure_filename
import base64

# Configuration de Flask et du dossier d'upload
app = Flask(__name__)
app.secret_key = 'supersecretkey'
UPLOAD_FOLDER = 'files'
ALLOWED_EXTENSIONS = {'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DB_PATH = 'urls.db'

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_db():
    if not os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('CREATE TABLE urls (id TEXT PRIMARY KEY, target_url TEXT)')
        conn.commit()
        conn.close()

init_db()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    target_url = request.form['target_url']
    fill_color = request.form['fill_color']
    back_color = request.form['back_color']

    unique_id = str(uuid.uuid4())[:8]

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO urls (id, target_url) VALUES (?, ?)', (unique_id, target_url))
    conn.commit()
    conn.close()

    dynamic_url = request.host_url + 'redirect/' + unique_id

    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(dynamic_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fill_color, back_color=back_color)

    buf = io.BytesIO()
    img.save(buf, 'PNG')
    buf.seek(0)

    flash(f"QR Code créé avec succès pour l'identifiant : {unique_id}", "success")
    return send_file(buf, mimetype='image/png', as_attachment=True, download_name='qr_code.png')

@app.route('/redirect/<unique_id>')
def redirect_dynamic(unique_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT target_url FROM urls WHERE id = ?', (unique_id,))
    result = c.fetchone()
    conn.close()

    if result:
        return redirect(result[0])
    else:
        return "Lien invalide ou expiré.", 404

@app.route('/update/<unique_id>', methods=['GET', 'POST'])
def update(unique_id):
    if request.method == 'POST':
        new_url = request.form['new_url']
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('UPDATE urls SET target_url = ? WHERE id = ?', (new_url, unique_id))
        conn.commit()
        conn.close()
        flash('URL mise à jour !', 'success')
        return redirect(url_for('list_qr'))
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT target_url FROM urls WHERE id = ?', (unique_id,))
    result = c.fetchone()
    conn.close()

    if result:
        return render_template('update.html', unique_id=unique_id, target_url=result[0])
    else:
        return "ID non trouvé.", 404

@app.route('/list')
def list_qr():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, target_url FROM urls')
    rows = c.fetchall()
    conn.close()
    return render_template('list.html', qr_codes=rows)

@app.route('/delete/<unique_id>', methods=['POST'])
def delete(unique_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM urls WHERE id = ?', (unique_id,))
    conn.commit()
    conn.close()
    flash('QR Code supprimé.', 'success')
    return redirect(url_for('list_qr'))

@app.route('/pdf/<filename>')
def download_pdf(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Aucun fichier envoyé.', 'danger')
            return redirect(request.url)

        file = request.files['file']
        if file.filename == '':
            flash('Nom de fichier vide.', 'danger')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            # Génère un identifiant court
            unique_id = str(uuid.uuid4())[:8]

            # Crée une URL publique vers le fichier
            file_url = url_for('download_pdf', filename=filename, _external=True)

            # Enregistre dans la base de données
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('INSERT INTO urls (id, target_url) VALUES (?, ?)', (unique_id, file_url))
            conn.commit()
            conn.close()

            # Génère un QR code pour le PDF
            qr = qrcode.make(request.host_url + 'redirect/' + unique_id)
            buf = io.BytesIO()
            qr.save(buf, format='PNG')
            buf.seek(0)

            flash(f'PDF uploadé et QR Code généré avec succès ! (ID : {unique_id})', 'success')
            return send_file(buf, mimetype='image/png', as_attachment=True, download_name='qr_code.png')

        flash('Fichier non autorisé.', 'danger')
        return redirect(request.url)

    return render_template('upload.html')

if __name__ == '__main__':
    app.run(debug=True)
