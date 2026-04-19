import os
import re
import time
import requests
import pdfplumber
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
from pdf2image import convert_from_path

from pptx import Presentation
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ===== CLEAN KEY =====
def clean_key(key):
    if not key:
        return None
    return key.strip().strip('"').strip("'")

# ===== LOAD KEYS =====
def load_keys(prefix, max_keys=15):
    keys = []
    for i in range(1, max_keys + 1):
        raw = os.getenv(f"{prefix}{i}")
        key = clean_key(raw)
        if key:
            keys.append(key)
    return keys

BOT_TOKEN = clean_key(os.getenv("BOT_TOKEN"))
GROQ_KEYS = load_keys("GROQ_API_KEY")

# ===== KEY MANAGER =====
class KeyManager:
    def __init__(self, keys):
        self.keys = keys
        self.index = 0
        self.sleep_map = {}

    def get_key(self):
        for _ in range(len(self.keys)):
            key = self.keys[self.index]

            if key in self.sleep_map:
                if time.time() < self.sleep_map[key]:
                    self.index = (self.index + 1) % len(self.keys)
                    continue
                else:
                    del self.sleep_map[key]

            return key
        return None

    def mark_failed(self, key):
        print("⛔ Sleeping:", key[:10])
        self.sleep_map[key] = time.time() + 3600
        self.index = (self.index + 1) % len(self.keys)

groq_manager = KeyManager(GROQ_KEYS)

# ===== IMAGE =====
def enhance_image(img):
    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(2.5)
    img = img.filter(ImageFilter.SHARPEN)
    return img

# ===== DIRECT GROQ API =====
def call_groq(prompt):
    for _ in range(len(GROQ_KEYS)):
        key = groq_manager.get_key()
        if not key:
            break

        url = "https://api.groq.com/openai/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": "llama3-8b-8192",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3
        }

        # ===== RETRY SYSTEM =====
        for attempt in range(3):
            try:
                print(f"🔄 Try {attempt+1} with key {key[:8]}")

                res = requests.post(
                    url,
                    headers=headers,
                    json=data,
                    timeout=30
                )

                print("STATUS:", res.status_code)
                print("RAW:", res.text[:200])

                if res.status_code != 200:
                    time.sleep(2)
                    continue

                result = res.json()

                if "choices" not in result:
                    continue

                content = result["choices"][0]["message"]["content"]

                if content and len(content.strip()) > 5:
                    return content

            except Exception as e:
                print("ERROR:", e)
                time.sleep(2)

        groq_manager.mark_failed(key)

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

    cleaned = call_groq(clean_prompt)
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

    return call_groq(mcq_prompt)

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
    await update.message.reply_text("Text / Image / PDF bhejo")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = process_text(update.message.text)

    if not result:
        await update.message.reply_text("❌ AI failed (network/API issue)")
        return

    questions = re.split(r"\n(?=प्रश्न)", result)
    await make_ppt(update, questions)

# ===== MAIN =====
def main():
    print("🚀 Bot running...")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()

if __name__ == "__main__":
    main()
