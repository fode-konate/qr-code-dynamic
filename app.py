from flask import Flask, redirect, request, render_template, send_file, url_for, flash, send_from_directory
import qrcode
import io
import uuid
import sqlite3
import os
from werkzeug.utils import secure_filename

# Configuration
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
        c.execute('CREATE TABLE urls (id TEXT PRIMARY KEY, target_url TEXT, folder TEXT DEFAULT "Général")')
        conn.commit()
        conn.close()

def add_folder_column():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE urls ADD COLUMN folder TEXT DEFAULT 'Général'")
        conn.commit()
    except:
        pass
    conn.close()

init_db()
add_folder_column()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    target_url = request.form['target_url']
    fill_color = request.form['fill_color']
    back_color = request.form['back_color']
    folder = request.form.get('folder', 'Général')

    unique_id = str(uuid.uuid4())[:8]

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO urls (id, target_url, folder) VALUES (?, ?, ?)', (unique_id, target_url, folder))
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

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        print("➡️ Formulaire reçu")
        if 'file' not in request.files:
            flash('Aucun fichier envoyé.', 'danger')
            print("❌ Aucun fichier trouvé dans request.files")
            return redirect(request.url)

        file = request.files['file']
        if file.filename == '':
            flash('Nom de fichier vide.', 'danger')
            print("❌ Nom de fichier vide")
            return redirect(request.url)

        folder = request.form.get('folder', 'Général')
        print(f"📥 Réception du fichier : {file.filename} dans dossier : {folder}")

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            print(f"📁 Fichier sauvegardé sous : {file_path}")

            unique_id = str(uuid.uuid4())[:8]
            file_url = url_for('download_pdf', filename=filename, _external=True)

            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('INSERT INTO urls (id, target_url, folder) VALUES (?, ?, ?)', (unique_id, file_url, folder))
            conn.commit()
            conn.close()

            print(f"✅ QR Code généré pour ID : {unique_id}")
            qr = qrcode.make(request.host_url + 'redirect/' + unique_id)
            buf = io.BytesIO()
            qr.save(buf, format='PNG')
            buf.seek(0)

            flash(f'PDF uploadé et QR Code généré avec succès ! (ID : {unique_id})', 'success')
            return send_file(buf, mimetype='image/png', as_attachment=True, download_name='qr_code.png')

        flash('Fichier non autorisé.', 'danger')
        print("❌ Extension de fichier non autorisée")
        return redirect(request.url)

    return render_template('upload.html')

@app.route('/pdf/<filename>')
def download_pdf(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/update/<unique_id>', methods=['GET', 'POST'])
def update(unique_id):
    if request.method == 'POST':
        new_url = request.form['new_url']
        folder = request.form.get('folder', 'Général')

        if 'file' in request.files and request.files['file'].filename != '':
            file = request.files['file']
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                new_url = url_for('download_pdf', filename=filename, _external=True)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('UPDATE urls SET target_url = ?, folder = ? WHERE id = ?', (new_url, folder, unique_id))
        conn.commit()
        conn.close()
        flash('QR Code mis à jour !', 'success')
        return redirect(url_for('list_qr'))

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT target_url, folder FROM urls WHERE id = ?', (unique_id,))
    result = c.fetchone()
    conn.close()

    if result:
        return render_template('update.html', unique_id=unique_id, target_url=result[0], folder=result[1])
    else:
        return "ID non trouvé.", 404

@app.route('/list')
def list_qr():
    selected_folder = request.args.get('folder')

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if selected_folder:
        c.execute('SELECT id, target_url, folder FROM urls WHERE folder = ?', (selected_folder,))
    else:
        c.execute('SELECT id, target_url, folder FROM urls')
    rows = c.fetchall()

    c.execute('SELECT DISTINCT folder FROM urls')
    folders = [row[0] for row in c.fetchall()]
    conn.close()

    return render_template('list.html', qr_codes=rows, folders=folders, selected_folder=selected_folder)

@app.route('/delete/<unique_id>', methods=['POST'])
def delete(unique_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM urls WHERE id = ?', (unique_id,))
    conn.commit()
    conn.close()
    flash('QR Code supprimé.', 'success')
    return redirect(url_for('list_qr'))

if __name__ == '__main__':
    app.run(debug=True)
