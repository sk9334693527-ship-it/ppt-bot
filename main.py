import os
import re
import time
import pdfplumber
import pytesseract
import google.generativeai as genai
from groq import Groq
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

# ===== CONFIG =====
BOT_TOKEN = clean_key(os.getenv("BOT_TOKEN"))

GEMINI_KEYS = load_keys("GEMINI_API_KEY")
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
        print(f"⛔ Sleeping key: {key[:10]}")
        self.sleep_map[key] = time.time() + 3600
        self.index = (self.index + 1) % len(self.keys)

gemini_manager = KeyManager(GEMINI_KEYS)
groq_manager = KeyManager(GROQ_KEYS)

# ===== IMAGE =====
def enhance_image(img):
    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(2.5)
    img = img.filter(ImageFilter.SHARPEN)
    return img

# ===== GROQ MODELS (AUTO FALLBACK) =====
GROQ_MODELS = [
    "llama3-8b-8192",
    "mixtral-8x7b-32768"
]

# ===== AI =====
def generate_ai(prompt):

    print("Gemini Keys:", GEMINI_KEYS)
    print("Groq Keys:", GROQ_KEYS)

    # ===== GEMINI FIRST =====
    for _ in range(len(GEMINI_KEYS)):
        key = gemini_manager.get_key()
        if not key:
            break

        try:
            print("Using Gemini:", key[:10])

            genai.configure(api_key=key)
            model = genai.GenerativeModel("gemini-2.5-flash")

            res = model.generate_content(prompt)
            return res.text

        except Exception as e:
            print("Gemini ERROR:", str(e))
            gemini_manager.mark_failed(key)

    # ===== GROQ FALLBACK =====
    for _ in range(len(GROQ_KEYS)):
        key = groq_manager.get_key()
        if not key:
            break

        for model_name in GROQ_MODELS:
            try:
                print(f"Using Groq: {key[:10]} | Model: {model_name}")

                client = Groq(api_key=key)

                chat = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=model_name
                )

                return chat.choices[0].message.content

            except Exception as e:
                print("Groq ERROR:", str(e))

        groq_manager.mark_failed(key)

    print("❌ All AI sleeping or failed")
    return ""

# ===== PROMPT =====
FIX_PROMPT = """
तुम एक हिंदी MCQ generator हो।

काम:
1. दिए गए टेक्स्ट से केवल प्रश्न निकालो
2. मात्रा सुधारो
3. अर्थ वही रखो
4. MCQ format बनाओ

FORMAT:
प्रश्न ...
A)
B)
C)
D)

TEXT:
"""

# ===== PPT =====
async def make_ppt(update, questions):
    prs = Presentation()

    if not questions:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = "❌ No Data"
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
    await update.message.reply_text("📸 Image | ✍️ Text | 📄 PDF bhejo")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fixed = generate_ai(FIX_PROMPT + update.message.text)

    if not fixed:
        await update.message.reply_text("❌ AI failed")
        return

    questions = re.split(r"\n(?=प्रश्न)", fixed)
    await make_ppt(update, questions)

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Processing...")

    photo = update.message.photo[-1]
    file = await photo.get_file()

    path = "img.jpg"
    await file.download_to_drive(path)

    img = enhance_image(Image.open(path))
    text = pytesseract.image_to_string(img, lang="hin+eng")

    os.remove(path)

    if not text:
        await update.message.reply_text("❌ OCR fail")
        return

    fixed = generate_ai(FIX_PROMPT + text)

    if not fixed:
        await update.message.reply_text("❌ AI failed")
        return

    questions = re.split(r"\n(?=प्रश्न)", fixed)
    await make_ppt(update, questions)

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📄 Processing PDF...")

    file = await update.message.document.get_file()
    path = "file.pdf"
    await file.download_to_drive(path)

    all_text = ""

    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    all_text += text + "\n"

        if len(all_text.strip()) < 50:
            for i in range(1, 20):
                images = convert_from_path(path, dpi=300, first_page=i, last_page=i)
                if not images:
                    break

                img = enhance_image(images[0])
                text = pytesseract.image_to_string(img, lang="hin+eng")
                if text:
                    all_text += text + "\n"

        os.remove(path)

        if not all_text:
            await update.message.reply_text("❌ No text")
            return

        fixed = generate_ai(FIX_PROMPT + all_text)

        if not fixed:
            await update.message.reply_text("❌ AI failed")
            return

        questions = re.split(r"\n(?=प्रश्न)", fixed)
        await make_ppt(update, questions)

    except Exception as e:
        await update.message.reply_text(f"❌ ERROR: {e}")

# ===== MAIN =====
def main():
    print("🚀 Bot starting...")

    if not BOT_TOKEN:
        print("❌ BOT_TOKEN missing")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))

    app.run_polling()

if __name__ == "__main__":
    main()
