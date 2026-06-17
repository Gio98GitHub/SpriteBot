import os
import psycopg2
import hashlib
import hmac
import json
from urllib.parse import parse_qsl
from flask import Flask, request, jsonify, send_from_directory
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
import asyncio
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__, static_folder="static")

# Recupera le variabili configurate su Render
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROUP_CHAT_ID = os.environ.get("GROUP_CHAT_ID")
DATABASE_URL = os.environ.get("DATABASE_URL")

# Token segreto separato per validare le richieste del webhook Telegram.
# Va impostato con setWebhook (parametro secret_token) E come env var su Render.
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

# ---------------- RATE LIMITING ----------------

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["60 per minute"],
    storage_uri="memory://"
)

# ---------------- CONFIGURAZIONE SPIRITELLI ----------------

# Ogni tipo ha la sua emoji e la lista di varianti disponibili (con relativa emoji).
# 🥜 Arachide Bruciata ha SOLO la variante Normale.
# Tutti gli altri: Normale, Oro, Gommoso, Galassia (struttura pronta per differenziare in futuro).

VARIANTI_STANDARD = [
    {"id": "Normale", "icon": "🌱"},
    {"id": "Oro", "icon": "🪙"},
    {"id": "Gommoso", "icon": "🍬"},
    {"id": "Galassia", "icon": "🌌"},
]

VARIANTI_SOLO_NORMALE = [
    {"id": "Normale", "icon": "🌱"},
]

SPIRITELLI_CONFIG = {
    "Acqua": {"icon": "💧", "varianti": VARIANTI_STANDARD},
    "Fuoco": {"icon": "🔥", "varianti": VARIANTI_STANDARD},
    "Terra": {"icon": "🌍", "varianti": VARIANTI_STANDARD},
    "Papera": {"icon": "🦆", "varianti": VARIANTI_STANDARD},
    "Demone": {"icon": "😈", "varianti": VARIANTI_STANDARD},
    "Fantasma": {"icon": "👻", "varianti": VARIANTI_STANDARD},
    "Re": {"icon": "👑", "varianti": VARIANTI_STANDARD},
    "Punk": {"icon": "🎸", "varianti": VARIANTI_STANDARD},
    "Sogno": {"icon": "🌌", "varianti": VARIANTI_STANDARD},
    "Punto Zero": {"icon": "🔮", "varianti": VARIANTI_STANDARD},
    "Arachide Bruciata": {"icon": "🥜", "varianti": VARIANTI_SOLO_NORMALE},
}

# ---------------- DATABASE (Supabase/PostgreSQL) ----------------

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def aggiungi_spiritello(user_id, username, tipo, variante):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO collezione (user_id, username, tipo, variante)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id, tipo, variante) DO NOTHING
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
    """
    Verifica la firma HMAC dei dati ricevuti dalla Telegram WebApp.
    Ritorna il dizionario 'user' se valido, altrimenti None.
    """
    try:
        parsed = dict(parse_qsl(init_data))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None

        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new("WebAppData".encode(), BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        # Confronto a tempo costante per evitare timing attack
        if not hmac.compare_digest(calculated_hash, received_hash):
            return None

        return json.loads(parsed.get("user", "{}"))
    except Exception:
        return None

# ---------------- GESTIONE DEI COMANDI GRUPPO ----------------

async def rispondi_comando_gruppo(chat_id, message_id, testo_messaggio):
    bot = Bot(token=BOT_TOKEN)
    bot_info = await bot.get_me()
    bot_username = bot_info.username

    # Cerchiamo un @username dopo il comando per vedere se è una richiesta "guarda collezione di"
    parti = testo_messaggio.split()
    target_username = None

    for parte in parti:
        if parte.startswith("@") and parte != f"@{bot_username}":
            target_username = parte.replace("@", "")
            break

    if target_username:
        link_web_app = f"https://{request.host}/?view_user={target_username}"
        testo_risposta = f"👀 Clicca qui sotto per guardare la collezione di @{target_username}!"
        testo_bottone = f"🎒 Guarda Collezione di @{target_username}"
    else:
        link_web_app = f"https://t.me/{bot_username}"
        testo_risposta = "✨ Apri la chat privata col bot e premi il pulsante in basso per gestire la tua collezione di Spiritelli!"
        testo_bottone = "🎒 Apri SpiriBot"

    tastiera = InlineKeyboardMarkup([
        [InlineKeyboardButton(testo_bottone, url=link_web_app)]
    ])

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=testo_risposta,
            reply_to_message_id=message_id,
            reply_markup=tastiera
        )
    except Exception as e:
        print(f"Errore invio messaggio comando: {e}")

# ---------------- ROUTES STATICHE ----------------

@app.route("/")
def home():
    return send_from_directory("static", "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("static", path)

# ---------------- WEBHOOK TELEGRAM ----------------

@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    # Verifica il secret token impostato tramite setWebhook (header dedicato Telegram).
    # Se WEBHOOK_SECRET non è configurato, questo controllo viene saltato (compatibilità),
    # ma è FORTEMENTE consigliato impostarlo.
    if WEBHOOK_SECRET:
        header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(header_secret, WEBHOOK_SECRET):
            return jsonify({"status": "forbidden"}), 403

    update = request.get_json()
    if update and "message" in update:
        message = update["message"]
        text = message.get("text", "")
        chat_id = message["chat"]["id"]
        message_id = message["message_id"]

        if text.startswith("/spiritelli"):
            asyncio.run(rispondi_comando_gruppo(chat_id, message_id, text))

    return jsonify({"status": "ok"})

# ---------------- API ----------------

@app.route("/api/info")
def api_info():
    """Ritorna la configurazione di tipi/varianti per costruire i menu a cascata nel frontend."""
    risposta = {}
    for tipo, dati in SPIRITELLI_CONFIG.items():
        risposta[tipo] = {
            "icon": dati["icon"],
            "varianti": dati["varianti"]
        }
    return jsonify(risposta)

@app.route("/api/collezione", methods=["POST"])
@limiter.limit("30 per minute")
def api_collezione():
    body = request.get_json()
    user = verifica_init_data(body.get("initData", ""))
    if not user:
        return jsonify({"error": "non autorizzato"}), 401

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT tipo, variante FROM collezione WHERE user_id = %s", (user["id"],))
    rows = c.fetchall()
    conn.close()
    return jsonify({"spiritelli": [{"tipo": r[0], "variante": r[1]} for r in rows]})

@app.route("/api/collezione_utente", methods=["POST"])
@limiter.limit("30 per minute")
def api_collezione_utente():
    """
    Vista in sola lettura della collezione di un altro utente, tramite username.
    Non richiede autenticazione (è read-only e dati non sensibili).
    """
    username_target = request.args.get("username", "").lstrip("@").strip()
    if not username_target:
        return jsonify({"error": "username mancante"}), 400

    conn = get_db_connection()
    c = conn.cursor()
    # Ricerca case-insensitive per essere più robusto
    c.execute("SELECT tipo, variante FROM collezione WHERE LOWER(username) = LOWER(%s)", (username_target,))
    rows = c.fetchall()
    conn.close()
    
    return jsonify({"spiritelli": [{"tipo": r[0], "variante": r[1]} for r in rows]})

@app.route("/api/aggiungi", methods=["POST"])
@limiter.limit("20 per minute")
def api_aggiungi():
    body = request.get_json()
    user = verifica_init_data(body.get("initData", ""))
    if not user:
        return jsonify({"error": "non autorizzato"}), 401

    tipo, variante = body.get("tipo"), body.get("variante")

    if tipo not in SPIRITELLI_CONFIG:
        return jsonify({"error": "tipo non valido"}), 400

    varianti_valide = [v["id"] for v in SPIRITELLI_CONFIG[tipo]["varianti"]]
    if variante not in varianti_valide:
        return jsonify({"error": "variante non valida per questo tipo"}), 400

    success = aggiungi_spiritello(user["id"], user.get("username", "utente"), tipo, variante)
    return jsonify({"ok": success})

@app.route("/api/elimina", methods=["POST"])
@limiter.limit("20 per minute")
def api_elimina():
    body = request.get_json()
    user = verifica_init_data(body.get("initData", ""))
    if not user:
        return jsonify({"error": "non autorizzato"}), 401

    tipo, variante = body.get("tipo"), body.get("variante")

    if tipo not in SPIRITELLI_CONFIG:
        return jsonify({"error": "tipo non valido"}), 400

    varianti_valide = [v["id"] for v in SPIRITELLI_CONFIG[tipo]["varianti"]]
    if variante not in varianti_valide:
        return jsonify({"error": "variante non valida per questo tipo"}), 400

    ok = elimina_spiritello(user["id"], tipo, variante)
    return jsonify({"ok": ok})

@app.route("/api/richiedi", methods=["POST"])
@limiter.limit("5 per minute")
def api_richiedi():
    body = request.get_json()
    user = verifica_init_data(body.get("initData", ""))
    if not user:
        return jsonify({"error": "non autorizzato"}), 401

    tipo, variante = body.get("tipo"), body.get("variante")

    if tipo not in SPIRITELLI_CONFIG:
        return jsonify({"error": "tipo non valido"}), 400

    varianti_valide = [v["id"] for v in SPIRITELLI_CONFIG[tipo]["varianti"]]
    if variante not in varianti_valide:
        return jsonify({"error": "variante non valida per questo tipo"}), 400

    icon_tipo = SPIRITELLI_CONFIG[tipo]["icon"]
    icon_variante = next(
        (v["icon"] for v in SPIRITELLI_CONFIG[tipo]["varianti"] if v["id"] == variante), "✨"
    )

    testo = (
        f"🔎 @{user.get('username', 'utente')} cerca uno spiritello!\n\n"
        f"{icon_tipo} Tipo: {tipo}\n"
        f"{icon_variante} Variante: {variante}\n\n"
        f"💬 Se lo possiedi e vuoi scambiarlo, rispondi a questo messaggio!"
    )
    asyncio.run(invia_messaggio_gruppo(testo))
    return jsonify({"ok": True})

async def invia_messaggio_gruppo(testo):
    bot = Bot(token=BOT_TOKEN)
    await bot.send_message(chat_id=GROUP_CHAT_ID, text=testo)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
