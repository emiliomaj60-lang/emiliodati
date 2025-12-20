from flask import Flask, render_template_string, request
import requests
import json
import datetime
import os

app = Flask(__name__)

# CONFIGURAZIONE
GITHUB_TOKEN = os.getenv("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")
GITHUB_USER = "emiliomaj60-lang"   # <-- metti il tuo username GitHub
REPO_NAME = "alpini-app"           # <-- metti il nome del nuovo repo pubblico
FOLDER = "ALPINI"

# TEMPLATE HTML SEMPLICE
HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Ordini Alpini</title>
    <style>
        body { font-family: Arial; padding: 20px; }
        input[type=number] { width: 60px; }
        button { padding: 10px; margin-top: 20px; }
    </style>
</head>
<body>
    <h2>Ordini Alpini</h2>
    <form method="POST">
        <label>Nome cliente:</label><br>
        <input type="text" name="cliente" required><br><br>

        {% for item in menu %}
            <label>{{ item['nome'] }} ({{ item['prezzo'] }}€)</label>
            <input type="number" name="{{ item['nome'] }}" min="0" value="0"><br>
        {% endfor %}

        <button type="submit">Invia ordine</button>
    </form>
</body>
</html>
"""

# FUNZIONE: legge menu CSV dal repo
def get_menu():
    url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{REPO_NAME}/main/{FOLDER}/menu_alpini.csv"
    r = requests.get(url)
    lines = r.text.splitlines()
    menu = []
    for line in lines[1:]:
        nome, prezzo = line.split(",")
        menu.append({"nome": nome, "prezzo": float(prezzo)})
    return menu

# FUNZIONE: legge contatore
def get_counter():
    url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{REPO_NAME}/main/{FOLDER}/counter.json"
    r = requests.get(url)
    return json.loads(r.text)["counter"]

# FUNZIONE: aggiorna contatore
def update_counter(new_value):
    url = f"https://api.github.com/repos/{GITHUB_USER}/{REPO_NAME}/contents/{FOLDER}/counter.json"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    content = json.dumps({"counter": new_value})
    encoded = content.encode("utf-8").decode("utf-8")

    get_file = requests.get(url, headers=headers).json()
    sha = get_file["sha"]

    data = {
        "message": "Update counter",
        "content": encoded.encode("utf-8").hex(),
        "sha": sha
    }

    requests.put(url, headers=headers, data=json.dumps(data))

# FUNZIONE: salva ordine CSV
def save_order(cliente, items, totale, numero):
    filename = f"{FOLDER}/ordine_{numero}_{cliente}.csv"
    url = f"https://api.github.com/repos/{GITHUB_USER}/{REPO_NAME}/contents/{filename}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    csv = "prodotto,quantità,prezzo_totale\n"
    for nome, qta, prezzo in items:
        csv += f"{nome},{qta},{prezzo}\n"
    csv += f"Totale,,{totale}\n"

    encoded = csv.encode("utf-8").decode("utf-8")

    data = {
        "message": "Nuovo ordine",
        "content": encoded.encode("utf-8").hex()
    }

    requests.put(url, headers=headers, data=json.dumps(data))

@app.route("/", methods=["GET", "POST"])
def index():
    menu = get_menu()

    if request.method == "POST":
        cliente = request.form["cliente"]
        items = []
        totale = 0

        for item in menu:
            qta = int(request.form.get(item["nome"], 0))
            if qta > 0:
                prezzo = qta * item["prezzo"]
                totale += prezzo
                items.append((item["nome"], qta, prezzo))

        numero = get_counter() + 1
        update_counter(numero)

        save_order(cliente, items, totale, numero)

        return f"Ordine inviato! Numero ordine: {numero}"

    return render_template_string(HTML, menu=menu)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
