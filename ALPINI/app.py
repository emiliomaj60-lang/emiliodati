import os
import io
import csv
import base64
import json
import time
import threading
from datetime import datetime
from flask import Flask, request, render_template_string
import requests

# Config GitHub fissi per il tuo repo
GITHUB_TOKEN = os.environ.get("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")
GITHUB_OWNER = "emiliomaj60-lang"
GITHUB_REPO = "emiliodati"
MENU_PATH = "ALPINI/menu_alpini.csv"
COUNTER_PATH = "ALPINI/counter.json"
ORDERS_DIR = "ALPINI"   # cartella unica per menu, counter e ordini

app = Flask(__name__)
lock = threading.Lock()

GITHUB_API = "https://api.github.com"
RAW_BASE = "https://raw.githubusercontent.com"

def gh_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

def get_raw_url(path):
    return f"{RAW_BASE}/{GITHUB_OWNER}/{GITHUB_REPO}/main/{path}"

def get_contents_url(path):
    return f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}"

def read_menu():
    r = requests.get(get_raw_url(MENU_PATH))
    r.raise_for_status()
    reader = csv.DictReader(io.StringIO(r.text))
    items = []
    for row in reader:
        name = (row.get("nome_pietanza") or row.get("name") or "").strip()
        price_raw = row.get("prezzo") or row.get("price") or "0"
        price = float(str(price_raw).replace(",", "."))
        if name:
            items.append({"name": name, "price": price})
    return items

def read_counter():
    r = requests.get(get_contents_url(COUNTER_PATH), headers=gh_headers())
    if r.status_code == 404:
        return {"value": 0, "sha": None}
    r.raise_for_status()
    data = r.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return {"value": json.loads(content)["value"], "sha": data["sha"]}

def write_counter(new_value, prev_sha):
    payload = {
        "message": f"Incremento contatore a {new_value}",
        "content": base64.b64encode(json.dumps({"value": new_value}).encode("utf-8")).decode("utf-8"),
        "branch": "main"
    }
    if prev_sha:
        payload["sha"] = prev_sha
    r = requests.put(get_contents_url(COUNTER_PATH), headers=gh_headers(), json=payload)
    if r.status_code in (200, 201):
        return r.json()["content"]["sha"]
    elif r.status_code == 409:
        raise RuntimeError("Counter conflict")
    r.raise_for_status()

def write_order_file(filename, csv_text):
    payload = {
        "message": f"Aggiungi ordine {filename}",
        "content": base64.b64encode(csv_text.encode("utf-8")).decode("utf-8"),
        "branch": "main"
    }
    r = requests.put(get_contents_url(f"{ORDERS_DIR}/{filename}"), headers=gh_headers(), json=payload)
    r.raise_for_status()

# --- Template HTML (uguale a prima, responsive per smartphone) ---
# ... [mantieni INDEX_TPL e CONFIRM_TPL come nella versione precedente] ...

@app.route("/", methods=["GET"])
def index():
    items = read_menu()
    return render_template_string(INDEX_TPL, items=items)

@app.route("/submit", methods=["POST"])
def submit():
    items = []
    idx = 0
    total = 0.0
    while True:
        name_key = f"name_{idx}"
        price_key = f"price_{idx}"
        qty_key = f"qty_{idx}"
        if name_key not in request.form:
            break
        name = request.form[name_key]
        price = float(request.form[price_key])
        qty = int(request.form.get(qty_key, "0") or "0")
        if qty > 0:
            partial = price * qty
            items.append((name, qty, price, partial))
            total += partial
        idx += 1

    customer = request.form.get("customer", "").strip()
    if not customer:
        return "Nome cliente mancante", 400

    # Concorrenza: lock + retry su counter
    attempts = 0
    while True:
        attempts += 1
        with lock:
            counter = read_counter()
            new_value = counter["value"] + 1
            try:
                new_sha = write_counter(new_value, counter["sha"])
                order_number = new_value
                break
            except RuntimeError:
                if attempts >= 5:
                    return "Conflitto persistente sul contatore, riprovare.", 409
                time.sleep(0.2)

    # File ordine
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    safe_name = "".join(c for c in customer if c.isalnum() or c in ("-", "_")).strip() or "Cliente"
    filename = f"{ts}_{safe_name}_{order_number:06d}.csv"
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["pietanza", "quantita", "prezzo_unitario", "parziale"])
    for name, qty, price, partial in items:
        w.writerow([name, qty, f"{price:.2f}", f"{partial:.2f}"])
    w.writerow([])
    w.writerow(["Totale", "", "", f"{total:.2f}"])

    write_order_file(filename, out.getvalue())

    return render_template_string(CONFIRM_TPL, order_number=order_number, customer=customer, total=total)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
