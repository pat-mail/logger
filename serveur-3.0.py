from flask import Flask, request, jsonify, render_template_string
import sqlite3
from datetime import datetime
import urllib

app = Flask(__name__)
DB_NAME = 'mesures_bme280.db'

# HTML de la page d'accueil
HTML_PAGE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Données capteurs ESP</title>
</head>
<body>
    <h1>Données capteurs ESP (extrait)</h1>
    <ul>
        <li><a href="/data">Voir les 24 dernières mesures de chaque ESP</a></li>
    </ul>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/data')
def get_data():
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute("SELECT DISTINCT device FROM mesures")
        devices = [row[0] for row in cur.fetchall()]

        html_output = "<h1>Données : 24 dernières mesures par appareil</h1>"

        for device in devices:
            cur.execute("""
                SELECT device, temperature, humidity, pressure, timestamp
                FROM mesures
                WHERE device = ?
                ORDER BY datetime(timestamp) DESC
                LIMIT 24
            """, (device,))
            rows = cur.fetchall()

            html_output += f"<h2>Appareil : {device}</h2>"
            html_output += """
                <table border="1" cellpadding="4" cellspacing="0">
                    <tr>
                        <th>Horodatage</th>
                        <th>Température (°C)</th>
                        <th>Humidité (%)</th>
                        <th>Pression (hPa)</th>
                    </tr>
            """

            for row in reversed(rows):
                html_output += f"""
                    <tr>
                        <td>{row['timestamp']}</td>
                        <td>{row['temperature']}</td>
                        <td>{row['humidity']}</td>
                        <td>{row['pressure']}</td>
                    </tr>
                """

            html_output += "</table><br>"

        conn.close()
        return html_output

    except Exception as e:
        print(f"Erreur dans /data : {e}")
        return f"Erreur serveur : {e}", 500

@app.route('/receive_batch', methods=['POST'])
def receive_batch():
    try:
        data = request.get_json()
        if not data:
            return "Aucune donnée reçue ou format incorrect", 400

        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()

        for entry in data:
            cur.execute("""
                INSERT INTO mesures (device, temperature, humidity, pressure, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (
                entry.get('device'),
                entry.get('temperature'),
                entry.get('humidity'),
                entry.get('pressure'),
                entry.get('timestamp')
            ))

        conn.commit()
        conn.close()
        return "Données insérées avec succès", 200

    except Exception as e:
        print(f"Erreur dans /receive_batch : {e}")
        return f"Erreur serveur : {e}", 500

@app.route('/routes')
def list_routes():
    output = []
    for rule in app.url_map.iter_rules():
        methods = ','.join(rule.methods)
        line = urllib.parse.unquote(f"{rule.endpoint}: {methods} {rule}")
        output.append(line)
    return '<br>'.join(sorted(output))
    
@app.route('/time')
def get_time():
    now = datetime.now()
    return jsonify({
        "year": now.year,
        "month": now.month,
        "day": now.day,
        "hour": now.hour,
        "minute": now.minute
    })



if __name__ == '__main__':
    print("Démarrage du serveur Flask...")
    app.run(host='0.0.0.0', port=5000, debug=True)
