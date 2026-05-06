import os
import json
import logging
import base64
import random
import io
from datetime import time
import httpx
from PIL import Image, ImageDraw, ImageFont
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

GRADIENTS = [
    [(147, 51, 234), (236, 72, 153)],    # viola -> rosa
    [(249, 115, 22), (234, 179, 8)],      # arancio -> giallo
    [(59, 130, 246), (16, 185, 129)],     # blu -> verde
    [(236, 72, 153), (248, 113, 113)],    # rosa -> rosso
    [(99, 102, 241), (139, 92, 246)],     # indigo -> viola
    [(20, 184, 166), (59, 130, 246)],     # teal -> blu
    [(239, 68, 68), (249, 115, 22)],      # rosso -> arancio
    [(168, 85, 247), (59, 130, 246)],     # viola -> blu
]

STYLE_FORMATS = {
    "assurdo": "assurdo surreale — contrasto brutale tra premessa e conclusione",
    "preferiresti": "formato 'preferiresti X / 0 / Y' dove Y è sempre peggio di quanto immaginabile",
    "date idea": "formato 'date idea:' seguito da sequenza di attività sempre più assurde",
    "confessione": "confessione diretta senza filtri, più caotica man mano che va avanti",
    "update": "update in prima persona su una situazione ridicola già in corso",
}

SYSTEM_PROMPT = """Sei un generatore di testi per meme italiani sul dating e le relazioni.

REFERENCE DI STILE (da usare come base):
{REFS}

TOPIC: esclusivamente dating, relazioni, situationship, app di incontri, dinamiche tra persone, ghosting, red flag, dipendenza emotiva, attrazione, rotture, sesso. Niente altro.

REGOLE FISSE:
- Tono: confessione diretta, contrasto brutale, assurdo che scala senza preavviso
- Linguaggio colloquiale italiano, slang naturale, mix italiano/inglese quando cade bene
- La battuta sta nel gap tra premessa banale e conclusione estrema o surreale
- Mai spiegare la battuta. Mai moralizzare. Mai essere gentile o rassicurante.
- Struttura spesso: setup → pausa o "0" → punch completamente fuori scala
- Formati usati: "preferiresti X / 0 / Y", "date idea: ...", confessione one-liner, "update: ..."
- Comicità ESTREMA — non fermarti prima del baratro
- Parla sempre in prima persona o in modo diretto, come se fossi dentro la situazione

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

def make_gradient(w, h, c1, c2):
    img = Image.new("RGB", (w, h))
    for y in range(h):
        t = y / h
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        for x in range(w):
            img.putpixel((x, y), (r, g, b))
    return img

def generate_meme_image(text):
    W, H = 1080, 1080
    colors = random.choice(GRADIENTS)
    img = make_gradient(W, H, colors[0], colors[1])
    draw = ImageDraw.Draw(img)

    font_size = 72
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except:
        font = ImageFont.load_default()

    margin = 80
    max_w = W - margin * 2

    def wrap_text(text, font, max_width):
        lines = []
        for paragraph in text.split("\n"):
            words = paragraph.split()
            if not words:
                lines.append("")
                continue
            line = ""
            for word in words:
                test = (line + " " + word).strip()
                bbox = draw.textbbox((0, 0), test, font=font)
                if bbox[2] - bbox[0] <= max_width:
                    line = test
                else:
                    if line:
                        lines.append(line)
                    line = word
            if line:
                lines.append(line)
        return lines

    lines = wrap_text(text, font, max_w)
    line_h = font_size + 16
    total_h = len(lines) * line_h
    y = (H - total_h) // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        x = (W - lw) // 2
        draw.text((x + 3, y + 3), line, font=font, fill=(0, 0, 0, 80))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += line_h

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

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
                "model": "claude-sonnet-4-6",
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
        "/refs — vedi ref caricate\n"
        "/salvati — vedi testi salvati\n\n"
        "Scrivi testo → salvato come ref\n"
        "Manda foto/screenshot → estraggo il testo\n"
        "/salva1-5 → genera anche l'immagine pronta",
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
            await update.message.reply_text(f"{meme}\n\n/salva{i+1} per salvarlo e generare l'immagine")
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
        msg = await update.message.reply_text("✅ salvato — genero l'immagine...")
        try:
            img_buf = generate_meme_image(meme)
            await update.message.reply_photo(photo=img_buf)
            await msg.delete()
        except Exception as e:
            logger.error(e)
            await msg.edit_text("✅ salvato — errore immagine, riprova con /img")
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
        f"✅ ref salvata ({len(data['refs'])} totali)"
    )

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 leggo l'immagine...")
    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        img_bytearray = await file.download_as_bytearray()
        img_bytes = bytes(img_bytearray)
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 500,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}},
                            {"type": "text", "text": "Estrai solo il testo scritto in questa immagine, esattamente come appare. Nessun commento, solo il testo."}
                        ]
                    }]
                }
            )
            extracted = response.json()["content"][0]["text"].strip()
        data = load_data()
        data["refs"].append(extracted)
        save_data(data)
        await msg.edit_text(
            f"✅ ref estratta e salvata ({len(data['refs'])} totali):\n\n_{extracted[:200]}_",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(e)
        await msg.edit_text("❌ non sono riuscito a leggere l'immagine")

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
            await context.bot.send_message(chat_id=CHAT_ID, text=f"{meme}\n\n/salva{i+1}")
    except Exception as e:
        logger.error(f"Daily job error: {e}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("genera", genera))
    app.add_handler(CommandHandler("stile", stile))
    app.add_handler(CommandHandler("refs", refs_list))
    app.add_handler(CommandHandler("salvati", salvati))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^/salva\d+$"), salva_handler))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^/setstile\d+$"), setstile_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    job_queue = app.job_queue
    job_queue.run_daily(daily_job, time=time(hour=9, minute=0))
    logger.info("Bot avviato")
    app.run_polling()

if __name__ == "__main__":
    main()
