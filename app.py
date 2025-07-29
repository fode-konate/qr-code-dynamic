from flask import Flask, redirect, request, render_template, send_file, url_for, flash, send_from_directory
import qrcode
import io
import uuid
import sqlite3
import os
from werkzeug.utils import secure_filename
import base64
from datetime import datetime
import csv

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
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS urls (
            id TEXT PRIMARY KEY,
            target_url TEXT,
            folder TEXT DEFAULT 'Général',
            filename TEXT,
            created_at TEXT,
            deleted INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    target_url = request.form['target_url']
    folder = request.form.get('folder', 'Général')
    fill_color = request.form.get('fill_color', '#000000')
    back_color = request.form.get('back_color', '#FFFFFF')

    unique_id = str(uuid.uuid4())[:8]
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO urls (id, target_url, folder, created_at)
        VALUES (?, ?, ?, ?)
    ''', (unique_id, target_url, folder, created_at))
    conn.commit()
    conn.close()

    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(request.host_url + 'redirect/' + unique_id)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fill_color, back_color=back_color)

    buf = io.BytesIO()
    img.save(buf, 'PNG')
    buf.seek(0)

    flash(f'QR Code créé pour : {unique_id}', 'success')
    return send_file(buf, mimetype='image/png', as_attachment=True, download_name=f'{unique_id}.png')

@app.route('/redirect/<unique_id>')
def redirect_dynamic(unique_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT target_url FROM urls WHERE id = ? AND deleted = 0', (unique_id,))
    result = c.fetchone()
    conn.close()
    if result:
        return redirect(result[0])
    return "QR Code non trouvé ou supprimé.", 404

@app.route('/list')
def list_qr():
    selected_folder = request.args.get('folder')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if selected_folder:
        c.execute("SELECT id, target_url, folder, filename, created_at FROM urls WHERE deleted = 0 AND folder = ?", (selected_folder,))
    else:
        c.execute("SELECT id, target_url, folder, filename, created_at FROM urls WHERE deleted = 0")
    rows = c.fetchall()
    c.execute("SELECT DISTINCT folder FROM urls WHERE deleted = 0")
    folders = [row[0] for row in c.fetchall()]
    conn.close()
    return render_template('list.html', qr_codes=rows, folders=folders, selected_folder=selected_folder)

@app.route('/delete/<unique_id>', methods=['POST'])
def delete(unique_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE urls SET deleted = 1 WHERE id = ?', (unique_id,))
    conn.commit()
    conn.close()
    flash('QR Code déplacé à la corbeille.', 'success')
    return redirect(url_for('list_qr'))

@app.route('/pdf/<filename>')
def download_pdf(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        file = request.files.get('file')
        folder = request.form.get('folder', 'Général')
        if not file or file.filename == '':
            flash('Aucun fichier sélectionné.', 'danger')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            unique_id = str(uuid.uuid4())[:8]
            file_url = url_for('download_pdf', filename=filename, _external=True)
            created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('''
                INSERT INTO urls (id, target_url, folder, filename, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (unique_id, file_url, folder, filename, created_at))
            conn.commit()
            conn.close()

            qr = qrcode.make(request.host_url + 'redirect/' + unique_id)
            buf = io.BytesIO()
            qr.save(buf, 'PNG')
            buf.seek(0)

            flash('PDF uploadé et QR Code généré avec succès !', 'success')
            return send_file(buf, mimetype='image/png', as_attachment=True, download_name=f'{unique_id}.png')

        flash('Fichier non autorisé.', 'danger')
        return redirect(request.url)
    return render_template('upload.html')

@app.route('/update/<unique_id>', methods=['GET', 'POST'])
def update(unique_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT target_url, folder FROM urls WHERE id = ?", (unique_id,))
    record = c.fetchone()
    conn.close()
    if not record:
        return "QR Code non trouvé.", 404

    if request.method == 'POST':
        new_url = request.form['new_url']
        folder = request.form.get('folder', 'Général')
        filename = None

        if 'file' in request.files and request.files['file'].filename != '':
            file = request.files['file']
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                new_url = url_for('download_pdf', filename=filename, _external=True)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        if filename:
            c.execute('UPDATE urls SET target_url = ?, folder = ?, filename = ? WHERE id = ?', (new_url, folder, filename, unique_id))
        else:
            c.execute('UPDATE urls SET target_url = ?, folder = ? WHERE id = ?', (new_url, folder, unique_id))
        conn.commit()
        conn.close()
        flash('QR Code mis à jour.', 'success')
        return redirect(url_for('list_qr'))

    return render_template('update.html', unique_id=unique_id, target_url=record[0], folder=record[1])

@app.route('/export')
def export_csv():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, target_url, folder, filename, created_at FROM urls WHERE deleted = 0')
    rows = c.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'URL', 'Dossier', 'Fichier', 'Créé le'])
    writer.writerows(rows)
    output.seek(0)

    return send_file(io.BytesIO(output.getvalue().encode()), mimetype='text/csv', as_attachment=True, download_name='qr_codes.csv')

if __name__ == '__main__':
    app.run(debug=True)
