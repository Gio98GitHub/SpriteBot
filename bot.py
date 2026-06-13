import os
import logging
from telegram import Update, WebAppInfo, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "INSERISCI_QUI_IL_TUO_TOKEN")
# URL HTTPS pubblico dove gira il backend (es. https://tuoapp.onrender.com)
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://tuoapp.onrender.com")


async def spiritelli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = ReplyKeyboardMarkup.from_button(
        KeyboardButton(
            text="👻 Apri Spiritelli",
            web_app=WebAppInfo(url=WEBAPP_URL)
        ),
        resize_keyboard=True
    )
    await update.message.reply_text(
        "Apri l'app per gestire la tua collezione di Spiritelli, "
        "aggiungere nuovi spiritelli o richiederne uno al gruppo!",
        reply_markup=keyboard
    )


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("spiritelli", spiritelli))
    app.run_polling()


if __name__ == "__main__":
    main()
