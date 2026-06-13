import os
import psycopg2
import hashlib
import hmac
import json
from urllib.parse import parse_qsl
from flask import Flask, request, jsonify, send_from_directory
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
import asyncio

app = Flask(__name__, static_folder="static")

# Recupera le variabili configurate su Render
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROUP_CHAT_ID = os.environ.get("GROUP_CHAT_ID")
DATABASE_URL = os.environ.get("DATABASE_URL")

# ---------------- CONFIGURAZIONE SPIRITELLI ----------------
SPIRITELLI_CONFIG = [
    "Acqua", "Terra", "Fuoco", "Papera", "Demone", 
    "Fantasma", "Re", "Punk", "Sogno", "Punto Zero", "Arachide Bruciata"
]
VARIANTI_LISTA = ["Normale", "Oro", "Caramella"]

# ---------------- DATABASE (Supabase/PostgreSQL) ----------------

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def aggiungi_spiritello(user_id, username, tipo, variante):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO collezione (user_id, username, tipo, variante) 
        VALUES (%s, %s, %s, %s) 
        ON CONFLICT DO NOTHING
    """, (user_id, username, tipo, variante))
    conn.commit()
    inserted = c.rowcount > 0
    conn.close()
    return inserted

def elimina_spiritello(user_id, tipo, variante):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM collezione WHERE user_id = %s AND tipo = %s AND variante = %s", 
              (user_id, tipo, variante))
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

# ---------------- NUOVA FUNZIONE PER GESTIRE IL COMANDO /SPIRITELLI ----------------

async def rispondi_comando_gruppo(chat_id, message_id):
    bot = Bot(token=BOT_TOKEN)
    bot_info = await bot.get_me()
    bot_username = bot_info.username
    
    # Questo link porta l'utente nella chat privata del bot, dove potrà aprire la Web App
    link_bot = f"https://t.me/{bot_username}"
    
    testo = "✨ Clicca sul pulsante qui sotto per aprire la tua collezione di Spiritelli!"
    tastiera = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎒 Apri SpiriBot", url=link_bot)]
    ])
    
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=testo,
            reply_to_message_id=message_id,  # Risponde direttamente all'utente che ha digitato il comando
            reply_markup=tastiera
        )
    except Exception as e:
        print(f"Errore invio messaggio comando: {e}")

# ---------------- API E GESTIONE WEBHOOK ----------------

@app.route("/")
def home(): return send_from_directory("static", "index.html")

# Nuovo endpoint per ricevere i messaggi da Telegram (Webhook)
@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = request.get_json()
    if "message" in update:
        message = update["message"]
        text = message.get("text", "")
        chat_id = message["chat"]["id"]
        message_id = message["message_id"]
        
        # Controlla se l'utente ha scritto /spiritelli o /spiritelli@NomeDelBot
        if text.startswith("/spiritelli"):
            asyncio.run(rispondi_comando_gruppo(chat_id, message_id))
            
    return jsonify({"status": "ok"})

@app.route("/api/collezione", methods=["POST"])
def api_collezione():
    body = request.get_json()
    user = verifica_init_data(body.get("initData", ""))
    if not user: return jsonify({"error": "non autorizzato"}), 401
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT tipo, variante FROM collezione WHERE user_id = %s", (user["id"],))
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
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
