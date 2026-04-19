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

# ===== ENV =====
def clean_key(key):
    if not key:
        return None
    return key.strip().strip('"').strip("'")

def load_keys(prefix, max_keys=15):
    keys = []
    for i in range(1, max_keys + 1):
        val = clean_key(os.getenv(f"{prefix}{i}"))
        if val:
            keys.append(val)
    return keys

BOT_TOKEN = clean_key(os.getenv("BOT_TOKEN"))
GROQ_KEYS = load_keys("GROQ_API_KEY")

# ===== KEY MANAGER =====
class KeyManager:
    def __init__(self, keys):
        self.keys = keys
        self.index = 0
        self.sleep = {}

    def get(self):
        for _ in range(len(self.keys)):
            key = self.keys[self.index]

            if key in self.sleep and time.time() < self.sleep[key]:
                self.index = (self.index + 1) % len(self.keys)
                continue

            return key
        return None

    def fail(self, key):
        print("⛔ Sleep key:", key[:10])
        self.sleep[key] = time.time() + 3600
        self.index = (self.index + 1) % len(self.keys)

manager = KeyManager(GROQ_KEYS)

# ===== IMAGE =====
def enhance(img):
    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(2.5)
    return img.filter(ImageFilter.SHARPEN)

# ===== MODELS =====
MODELS = [
    "mixtral-8x7b-32768",
    "llama3-8b-8192"
]

# ===== AI CALL =====
def call_ai(prompt):

    for _ in range(len(GROQ_KEYS)):
        key = manager.get()
        if not key:
            break

        for model in MODELS:
            for attempt in range(3):
                try:
                    print(f"🔄 Key:{key[:6]} Model:{model} Try:{attempt+1}")

                    res = requests.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.3
                        },
                        timeout=30
                    )

                    print("STATUS:", res.status_code)
                    print("RAW:", res.text[:150])

                    if res.status_code != 200:
                        time.sleep(2)
                        continue

                    data = res.json()

                    if "choices" not in data:
                        continue

                    content = data["choices"][0]["message"]["content"]

                    if content and len(content.strip()) > 10:
                        return content

                except Exception as e:
                    print("ERROR:", e)
                    time.sleep(2)

        manager.fail(key)

    return ""

# ===== PROCESS =====
def process_text(text):

    # STEP 1 CLEAN
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

    # STEP 2 MCQ
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

    if not questions:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = "No Data"
        slide.placeholders[1].text = "कुछ नहीं मिला"
    else:
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
    await update.message.reply_text("📄 Text | 📸 Image | PDF bhejo")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = process_text(update.message.text)

    if not result:
        await update.message.reply_text("❌ AI failed (logs dekho)")
        return

    questions = re.split(r"\n(?=प्रश्न)", result)
    await make_ppt(update, questions)

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Processing...")

    file = await update.message.photo[-1].get_file()
    path = "img.jpg"
    await file.download_to_drive(path)

    img = enhance(Image.open(path))
    text = pytesseract.image_to_string(img, lang="hin+eng")

    os.remove(path)

    result = process_text(text)

    if not result:
        await update.message.reply_text("❌ AI failed")
        return

    questions = re.split(r"\n(?=प्रश्न)", result)
    await make_ppt(update, questions)

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📄 Processing PDF...")

    file = await update.message.document.get_file()
    path = "file.pdf"
    await file.download_to_drive(path)

    text_all = ""

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_all += t + "\n"

    if len(text_all.strip()) < 50:
        images = convert_from_path(path, dpi=300)
        for img in images:
            text_all += pytesseract.image_to_string(enhance(img), lang="hin+eng")

    os.remove(path)

    result = process_text(text_all)

    if not result:
        await update.message.reply_text("❌ AI failed")
        return

    questions = re.split(r"\n(?=प्रश्न)", result)
    await make_ppt(update, questions)

# ===== MAIN =====
def main():
    print("🚀 Bot Started")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
