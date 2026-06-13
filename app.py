import os
import sqlite3
import hashlib
import hmac
import json
from urllib.parse import parse_qsl

from flask import Flask, request, jsonify, send_from_directory
from telegram import Bot
import asyncio

app = Flask(__name__, static_folder="static")
@app.route('/')
def home():
    return app.send_static_file('index.html')

BOT_TOKEN = os.environ.get("BOT_TOKEN", "INSERISCI_QUI_IL_TUO_TOKEN")
GROUP_CHAT_ID = os.environ.get("GROUP_CHAT_ID", "-1001234567890")

DB_PATH = "spiritelli.db"

# ---------------- CONFIGURAZIONE TIPI E VARIANTI ----------------

TIPI = {
    "Acqua": {"emoji": "💧", "icona": "ti-droplet"},
    "Aria": {"emoji": "🌬️", "icona": "ti-wind"},
    "Terra": {"emoji": "⛰️", "icona": "ti-mountain"},
}

VARIANTI_PER_TIPO = {
    "Acqua": [
        {"nome": "Normale", "emoji": "⚪"},
        {"nome": "Dorata", "emoji": "✨"},
        {"nome": "Gommosa", "emoji": "🟢"},
    ],
    "Aria": [
        {"nome": "Normale", "emoji": "⚪"},
        {"nome": "Dorata", "emoji": "✨"},
    ],
    "Terra": [
        {"nome": "Normale", "emoji": "⚪"},
        {"nome": "Gommosa", "emoji": "🟢"},
        {"nome": "Cristallina", "emoji": "💎"},
    ],
}

# ---------------- DATABASE ----------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS collezione (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            tipo TEXT NOT NULL,
            variante TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def aggiungi_spiritello(user_id, username, tipo, variante):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO collezione (user_id, username, tipo, variante) VALUES (?, ?, ?, ?)",
        (user_id, username, tipo, variante)
    )
    conn.commit()
    conn.close()

def get_collezione_raggruppata(user_id):
    """Ritorna la collezione raggruppata per tipo: {tipo: [{id, variante}, ...]}"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, tipo, variante FROM collezione WHERE user_id = ?", (user_id,))
    rows = c.fetchall()
    conn.close()

    raggruppata = {}
    for item_id, tipo, variante in rows:
        raggruppata.setdefault(tipo, []).append({"id": item_id, "variante": variante})
    return raggruppata

def get_collezione_raggruppata_username(username):
    """Stessa cosa ma cercando per username (per vedere collezione altri utenti)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT tipo, variante FROM collezione WHERE username = ? COLLATE NOCASE",
        (username,)
    )
    rows = c.fetchall()
    conn.close()

    raggruppata = {}
    for tipo, variante in rows:
        raggruppata.setdefault(tipo, []).append({"variante": variante})
    return raggruppata

def elimina_spiritello(item_id, user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM collezione WHERE id = ? AND user_id = ?", (item_id, user_id))
    conn.commit()
    deleted = c.rowcount
    conn.close()
    return deleted > 0

# ---------------- VALIDAZIONE TELEGRAM WEBAPP ----------------

def verifica_init_data(init_data: str):
    try:
        parsed = dict(parse_qsl(init_data))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None

        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed.items())
        )

        secret_key = hmac.new(
            "WebAppData".encode(), BOT_TOKEN.encode(), hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        if calculated_hash != received_hash:
            return None

        return json.loads(parsed.get("user", "{}"))
    except Exception:
        return None

# ---------------- ROUTES STATICHE (MINI APP) ----------------

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("static", path)

# ---------------- API ----------------

@app.route("/api/info")
def info():
    """Ritorna tipi e varianti con relative emoji/icone, per costruire i menu a cascata."""
    return jsonify({
        "tipi": [{"nome": t, "emoji": d["emoji"], "icona": d["icona"]} for t, d in TIPI.items()],
        "varianti_per_tipo": VARIANTI_PER_TIPO
    })

@app.route("/api/collezione")
def api_collezione():
    init_data = request.args.get("init_data", "")
    user = verifica_init_data(init_data)
    if not user:
        return jsonify({"error": "non autorizzato"}), 401

    raggruppata = get_collezione_raggruppata(user["id"])
    return jsonify(raggruppata)

@app.route("/api/collezione_utente")
def api_collezione_utente():
    """Vista in sola lettura della collezione di un altro utente, per username."""
    username = request.args.get("username", "").lstrip("@").strip()
    if not username:
        return jsonify({"error": "username richiesto"}), 400

    raggruppata = get_collezione_raggruppata_username(username)
    if not raggruppata:
        return jsonify({"error": "utente non trovato o collezione vuota"}), 404

    return jsonify({"username": username, "collezione": raggruppata})

@app.route("/api/aggiungi", methods=["POST"])
def api_aggiungi():
    body = request.get_json()
    init_data = body.get("init_data", "")
    user = verifica_init_data(init_data)
    if not user:
        return jsonify({"error": "non autorizzato"}), 401

    tipo = body.get("tipo")
    variante = body.get("variante")

    if tipo not in VARIANTI_PER_TIPO:
        return jsonify({"error": "tipo non valido"}), 400

    nomi_varianti = [v["nome"] for v in VARIANTI_PER_TIPO[tipo]]
    if variante not in nomi_varianti:
        return jsonify({"error": "variante non valida per questo tipo"}), 400

    username = user.get("username") or user.get("first_name", "utente")
    aggiungi_spiritello(user["id"], username, tipo, variante)
    return jsonify({"ok": True})

@app.route("/api/elimina", methods=["POST"])
def api_elimina():
    body = request.get_json()
    init_data = body.get("init_data", "")
    user = verifica_init_data(init_data)
    if not user:
        return jsonify({"error": "non autorizzato"}), 401

    item_id = body.get("id")
    ok = elimina_spiritello(item_id, user["id"])
    return jsonify({"ok": ok})

@app.route("/api/richiedi", methods=["POST"])
def api_richiedi():
    body = request.get_json()
    init_data = body.get("init_data", "")
    user = verifica_init_data(init_data)
    if not user:
        return jsonify({"error": "non autorizzato"}), 401

    tipo = body.get("tipo")
    variante = body.get("variante")

    if tipo not in VARIANTI_PER_TIPO:
        return jsonify({"error": "tipo non valido"}), 400

    nomi_varianti = [v["nome"] for v in VARIANTI_PER_TIPO[tipo]]
    if variante not in nomi_varianti:
        return jsonify({"error": "variante non valida per questo tipo"}), 400

    username = user.get("username")
    nome_display = f"@{username}" if username else user.get("first_name", "Un utente")

    emoji_tipo = TIPI[tipo]["emoji"]
    emoji_variante = next(
        (v["emoji"] for v in VARIANTI_PER_TIPO[tipo] if v["nome"] == variante), "✨"
    )

    testo = (
        f"🔎 {nome_display} sta cercando uno spiritello!\n\n"
        f"{emoji_tipo} Tipo: {tipo}\n"
        f"{emoji_variante} Variante: {variante}\n\n"
        f"💬 Se lo possiedi e vuoi scambiarlo, rispondi a questo messaggio!"
    )

    asyncio.run(invia_messaggio_gruppo(testo))
    return jsonify({"ok": True})

async def invia_messaggio_gruppo(testo):
    bot = Bot(token=BOT_TOKEN)
    await bot.send_message(chat_id=GROUP_CHAT_ID, text=testo)

# ---------------- MAIN ----------------

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
