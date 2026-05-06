import os
import json
import logging
import asyncio
from datetime import time
import httpx
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
CHAT_ID = os.environ.get("CHAT_ID")
DATA_FILE = "data.json"

STYLE_FORMATS = {
    "assurdo": "assurdo surreale — contrasto brutale tra premessa e conclusione",
    "preferiresti": "formato 'preferiresti X / 0 / Y' dove Y è sempre peggio di quanto immaginabile",
    "date idea": "formato 'date idea:' seguito da sequenza di attività sempre più assurde",
    "confessione": "confessione diretta senza filtri, più caotica man mano che va avanti",
    "update": "update in prima persona su una situazione ridicola già in corso",
}

SYSTEM_PROMPT = """Sei un generatore di testi per meme italiani virali. 

REFERENCE DI STILE (da usare come base):
{REFS}

REGOLE FISSE:
- Tono: confessione diretta, contrasto brutale, assurdo che scala senza preavviso
- Linguaggio colloquiale italiano, slang naturale, mix italiano/inglese quando cade bene
- La battuta sta nel gap tra premessa banale e conclusione estrema o surreale
- Mai spiegare la battuta. Mai moralizzare. Mai essere gentile o rassicurante.
- Struttura spesso: setup → pausa o "0" → punch completamente fuori scala
- Formati usati: "preferiresti X / 0 / Y", "date idea: ...", confessione one-liner, "update: ..."
- Comicità ESTREMA — non fermarti prima del baratro

STILE SESSIONE: {STYLE}

FORMATO OUTPUT:
Genera esattamente 5 testi. Separali con ---
Zero numerazione, zero titoli, zero commenti. Solo i testi."""

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"refs": [], "saved": [], "current_style": "assurdo"}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def call_claude(refs, style):
    refs_text = "\n\n---\n\n".join(refs) if refs else "nessuna ref ancora — usa il tuo istinto"
    style_desc = STYLE_FORMATS.get(style, style)
    prompt = SYSTEM_PROMPT.replace("{REFS}", refs_text).replace("{STYLE}", style_desc)

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-opus-4-5",
                "max_tokens": 1000,
                "system": prompt,
                "messages": [{"role": "user", "content": "Genera 5 testi meme. Sii brutalmente divertente."}]
            }
        )
        data = response.json()
        return data["content"][0]["text"]

def format_memes(raw_text):
    memes = [m.strip() for m in raw_text.split("---") if m.strip()]
    return memes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎲 *Hora Meme Lab*\n\n"
        "Comandi:\n"
        "/genera — 5 testi nuovi\n"
        "/stile — cambia formato\n"
        "/ref — aggiungi una reference\n"
        "/refs — vedi ref caricate\n"
        "/salvati — vedi testi salvati\n\n"
        "Oppure scrivi direttamente una ref e la salvo.",
        parse_mode="Markdown"
    )

async def genera(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    msg = await update.message.reply_text("⏳ sto generando...")

    try:
        raw = await call_claude(data["refs"], data["current_style"])
        memes = format_memes(raw)
        data["_last_generated"] = memes
        save_data(data)

        for i, meme in enumerate(memes):
            await update.message.reply_text(
                f"{meme}\n\n/salva{i+1} per salvarlo",
            )
        await msg.delete()
    except Exception as e:
        logger.error(e)
        await msg.edit_text("❌ errore, riprova")

async def salva_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.startswith("/salva"):
        return
    try:
        idx = int(text.replace("/salva", "")) - 1
    except:
        return
    data = load_data()
    last = data.get("_last_generated", [])
    if 0 <= idx < len(last):
        meme = last[idx]
        if meme not in data["saved"]:
            data["saved"].append(meme)
            save_data(data)
            await update.message.reply_text("✅ salvato")
        else:
            await update.message.reply_text("già salvato")
    else:
        await update.message.reply_text("non trovato, genera prima")

async def stile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stili = list(STYLE_FORMATS.keys())
    testo = "Scegli stile:\n\n" + "\n".join([f"/setstile{i+1} — {s}" for i, s in enumerate(stili)])
    await update.message.reply_text(testo)

async def setstile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.startswith("/setstile"):
        return
    try:
        idx = int(text.replace("/setstile", "")) - 1
    except:
        return
    stili = list(STYLE_FORMATS.keys())
    if 0 <= idx < len(stili):
        data = load_data()
        data["current_style"] = stili[idx]
        save_data(data)
        await update.message.reply_text(f"✅ stile impostato: *{stili[idx]}*", parse_mode="Markdown")

async def ref_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Scrivi la ref direttamente in chat e la salvo.\n\n"
        "Può essere un testo di meme, una situazione, un'osservazione — qualsiasi cosa."
    )

async def refs_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not data["refs"]:
        await update.message.reply_text("nessuna ref caricata ancora")
        return
    testo = f"📚 {len(data['refs'])} ref caricate:\n\n"
    for i, r in enumerate(data["refs"]):
        preview = r[:60] + "…" if len(r) > 60 else r
        testo += f"{i+1}. {preview}\n"
    await update.message.reply_text(testo)

async def salvati(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not data["saved"]:
        await update.message.reply_text("nessun testo salvato ancora")
        return
    for i, m in enumerate(data["saved"]):
        await update.message.reply_text(f"💾 {i+1}/{len(data['saved'])}\n\n{m}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.startswith("/"):
        return
    data = load_data()
    data["refs"].append(text)
    save_data(data)
    await update.message.reply_text(
        f"✅ ref salvata ({len(data['refs'])} totali)\n\nUsa /genera per produrre testi con il nuovo stile."
    )

async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    if not CHAT_ID:
        return
    data = load_data()
    try:
        raw = await call_claude(data["refs"], data["current_style"])
        memes = format_memes(raw)
        data["_last_generated"] = memes
        save_data(data)

        await context.bot.send_message(chat_id=CHAT_ID, text="☀️ *testi del giorno*", parse_mode="Markdown")
        for i, meme in enumerate(memes):
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=f"{meme}\n\n/salva{i+1}"
            )
    except Exception as e:
        logger.error(f"Daily job error: {e}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("genera", genera))
    app.add_handler(CommandHandler("stile", stile))
    app.add_handler(CommandHandler("ref", ref_cmd))
    app.add_handler(CommandHandler("refs", refs_list))
    app.add_handler(CommandHandler("salvati", salvati))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^/salva\d+$"), salva_handler))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^/setstile\d+$"), setstile_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    job_queue = app.job_queue
    job_queue.run_daily(daily_job, time=time(hour=9, minute=0))

    logger.info("Bot avviato")
    app.run_polling()

if __name__ == "__main__":
    main()
