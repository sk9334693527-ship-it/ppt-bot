import os
import re
import time
import requests
from pptx import Presentation

from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ===== ENV CLEAN =====
def clean_key(key):
    if not key:
        return None
    return key.strip().strip('"').strip("'")

def load_keys(prefix, max_keys=5):
    keys = []
    for i in range(1, max_keys + 1):
        val = clean_key(os.getenv(f"{prefix}{i}"))
        if val:
            keys.append(val)
    return keys

BOT_TOKEN = clean_key(os.getenv("BOT_TOKEN"))
GROQ_KEYS = load_keys("GROQ_API_KEY")

# ===== KEY ROTATION =====
key_index = 0
def get_key():
    global key_index
    if not GROQ_KEYS:
        return None
    key = GROQ_KEYS[key_index]
    key_index = (key_index + 1) % len(GROQ_KEYS)
    return key

# ===== GROQ CALL =====
def call_ai(prompt):
    for _ in range(len(GROQ_KEYS)):
        key = get_key()
        if not key:
            break

        for attempt in range(3):
            try:
                res = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "llama3-8b-8192",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3
                    },
                    timeout=25
                )

                print("STATUS:", res.status_code)

                if res.status_code != 200:
                    time.sleep(2)
                    continue

                data = res.json()

                content = data["choices"][0]["message"]["content"]

                if content and len(content.strip()) > 10:
                    return content

            except Exception as e:
                print("ERROR:", e)
                time.sleep(2)

    return ""

# ===== 2 STEP AI =====
def process_text(text):

    clean_prompt = f"""
टेक्स्ट साफ करो:
- spelling ठीक करो
- extra हटाओ
- readable बनाओ

{text}
"""

    cleaned = call_ai(clean_prompt)
    if not cleaned:
        return None

    mcq_prompt = f"""
नीचे दिए गए टेक्स्ट से MCQ बनाओ

FORMAT:
प्रश्न ...
A)
B)
C)
D)

{cleaned}
"""

    return call_ai(mcq_prompt)

# ===== PPT =====
async def make_ppt(update, questions):
    prs = Presentation()

    for q in questions:
        lines = [l.strip() for l in q.split("\n") if l.strip()]
        if not lines:
            continue

        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = lines[0][:200]

        tf = slide.placeholders[1].text_frame
        tf.text = ""

        for l in lines[1:]:
            tf.add_paragraph().text = l

    file = "output.pptx"
    prs.save(file)

    with open(file, "rb") as f:
        await update.message.reply_document(InputFile(f))

    os.remove(file)

# ===== HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Text bhejo, MCQ PPT bana dunga 📄➡️📊")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    result = process_text(text)

    if not result:
        await update.message.reply_text("❌ AI failed (logs check karo)")
        return

    questions = re.split(r"\n(?=प्रश्न)", result)
    await make_ppt(update, questions)

# ===== MAIN =====
def main():
    print("🚀 Bot running...")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # 🔥 IMPORTANT (NO CONFLICT FIX)
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
