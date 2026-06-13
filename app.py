import os
import psycopg2
import hashlib
import hmac
import json
from urllib.parse import parse_qsl
from flask import Flask, request, jsonify, send_from_directory
from telegram import Bot
import asyncio

app = Flask(__name__, static_folder="static")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROUP_CHAT_ID = os.environ.get("GROUP_CHAT_ID")
DATABASE_URL = os.environ.get("DATABASE_URL")

SPIRITELLI_CONFIG = [
    "Acqua", "Terra", "Fuoco", "Papera", "Demone", 
    "Fantasma", "Re", "Punk", "Sogno", "Punto Zero", "Arachide Bruciata"
]
VARIANTI_LISTA = ["Normale", "Oro", "Caramella"]

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

@app.route("/")
def home(): return send_from_directory("static", "index.html")

@app.route("/api/aggiungi", methods=["POST"])
def api_aggiungi():
    body = request.get_json()
    user = verifica_init_data(body.get("initData", ""))
    if not user: return jsonify({"error": "non autorizzato"}), 401
    
    tipo, variante = body.get("tipo"), body.get("variante")
    
    # Blocco logica per Arachide
    if tipo == "Arachide Bruciata" and variante in ["Oro", "Caramella"]:
        return jsonify({"error": "Variante non disponibile"}), 400
        
    if tipo not in SPIRITELLI_CONFIG or variante not in VARIANTI_LISTA:
        return jsonify({"error": "dati non validi"}), 400
    
    success = aggiungi_spiritello(user["id"], user.get("username", "utente"), tipo, variante)
    return jsonify({"ok": success})

# (Le altre rotte api_collezione, api_elimina, api_richiedi restano invariate)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
