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

BOT_TOKEN = os.environ.get("BOT_TOKEN", "INSERISCI_QUI_IL_TUO_TOKEN")
GROUP_CHAT_ID = os.environ.get("GROUP_CHAT_ID", "-1001234567890")
DB_PATH = "spiritelli.db"

# ---------------- CONFIGURAZIONE SPIRITELLI UFFICIALI ----------------
# Aggiornato con gli 11 spiritelli del Capitolo 7
SPIRITELLI_CONFIG = {
    "Acqua": "💧", "Terra": "🌍", "Fuoco": "🔥", "Papera": "🦆", 
    "Demone": "😈", "Fantasma": "👻", "Re": "👑", "Punk": "🎸", 
    "Sogno": "🌌", "Punto Zero": "🔮", "Arachide Bruciata": "🥜"
}
VARIANTI_LISTA = ["Normale", "Oro", "Caramella"]

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
            variante TEXT NOT NULL,
            UNIQUE(user_id, tipo, variante) 
        )
    """)
    conn.commit()
    conn.close()

def aggiungi_spiritello(user_id, username, tipo, variante):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            "INSERT OR IGNORE INTO collezione (user_id, username, tipo, variante) VALUES (?, ?, ?, ?)",
            (user_id, username, tipo, variante)
        )
        conn.commit()
        return c.rowcount > 0 # Ritorna True se ha inserito davvero
    except:
        return False
    finally:
        conn.close()

def elimina_spiritello(user_id, tipo, variante):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM collezione WHERE user_id = ? AND tipo = ? AND variante = ?", (user_id, tipo, variante))
    conn.commit()
    deleted = c.rowcount > 0
    conn.close()
    return deleted

# ---------------- VALIDAZIONE TELEGRAM ----------------

def verifica_init_data(init_data: str):
    try:
        parsed = dict(parse_qsl(init_data))
        received_hash = parsed.pop("hash", None)
        if not received_hash: return None
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new("WebAppData".encode(), BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if calculated_hash != received_hash: return None
        return json.loads(parsed.get("user", "{}"))
    except: return None

# ---------------- API ----------------

@app.route("/")
def home(): return app.send_static_file('index.html')

@app.route("/api/collezione", methods=["POST"])
def api_collezione():
    body = request.get_json()
    user = verifica_init_data(body.get("initData", ""))
    if not user: return jsonify({"error": "non autorizzato"}), 401
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT tipo, variante FROM collezione WHERE user_id = ?", (user["id"],))
    rows = c.fetchall()
    conn.close()
    
    return jsonify({"spiritelli": [{"tipo": r[0], "variante": r[1]} for r in rows]})

@app.route("/api/aggiungi", methods=["POST"])
def api_aggiungi():
    body = request.get_json()
    user = verifica_init_data(body.get("initData", ""))
    if not user: return jsonify({"error": "non autorizzato"}), 401
    
    tipo, variante = body.get("tipo"), body.get("variante")
    if tipo not in SPIRITELLI_CONFIG or variante not in VARIANTI_LISTA:
        return jsonify({"error": "dati non validi"}), 400
    
    success = aggiungi_spiritello(user["id"], user.get("username", "utente"), tipo, variante)
    return jsonify({"ok": success})

@app.route("/api/elimina", methods=["POST"])
def api_elimina():
    body = request.get_json()
    user = verifica_init_data(body.get("initData", ""))
    if not user: return jsonify({"error": "non autorizzato"}), 401
    
    ok = elimina_spiritello(user["id"], body.get("tipo"), body.get("variante"))
    return jsonify({"ok": ok})

@app.route("/api/richiedi", methods=["POST"])
def api_richiedi():
    body = request.get_json()
    user = verifica_init_data(body.get("initData", ""))
    if not user: return jsonify({"error": "non autorizzato"}), 401
    
    tipo, variante = body.get("tipo"), body.get("variante")
    testo = f"🔎 @{user.get('username', 'utente')} cerca uno spiritello!\n\n{tipo} ({variante})"
    asyncio.run(invia_messaggio_gruppo(testo))
    return jsonify({"ok": True})

async def invia_messaggio_gruppo(testo):
    bot = Bot(token=BOT_TOKEN)
    await bot.send_message(chat_id=GROUP_CHAT_ID, text=testo)

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
