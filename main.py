import os
import re
import subprocess
import pdfplumber
import pytesseract
import google.generativeai as genai
import requests
import base64

from PIL import Image, ImageEnhance, ImageFilter
from pdf2image import convert_from_path

from pptx import Presentation
from pptx.util import Inches
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_AUTO_SIZE

from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ===== CONFIG =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
AICREDITS_KEY = os.getenv("AICREDITS_API_KEY")

# ===== GEMINI BACKUP =====
GEMINI_KEYS = [os.getenv("GEMINI_API_KEY")]
GEMINI_KEYS = [k for k in GEMINI_KEYS if k]

gemini_models = []
for key in GEMINI_KEYS:
    genai.configure(api_key=key)
    gemini_models.append(genai.GenerativeModel("gemini-2.5-flash"))

# ===== QUESTION EXTRACTOR (🔥 FIX) =====
def extract_questions(text):
    pattern = r"(प्रश्न\s*\d+.*?)(?=प्रश्न\s*\d+|$)"
    matches = re.findall(pattern, text, re.DOTALL)

    if matches:
        return [m.strip() for m in matches]

    pattern2 = r"(Q\.?\s*\d+.*?)(?=Q\.?\s*\d+|$)"
    matches2 = re.findall(pattern2, text, re.DOTALL)

    if matches2:
        return [m.strip() for m in matches2]

    return [text.strip()]

# ===== AICREDITS VISION =====
def generate_vision(image_path):
    try:
        url = "https://api.aicredits.in/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {AICREDITS_KEY}",
            "Content-Type": "application/json"
        }

        with open(image_path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode()

        data = {
            "model": "openai/gpt-4o-mini",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "इस image से साफ और पूरा MCQ बनाओ"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_base64}"
                            }
                        }
                    ]
                }
            ]
        }

        res = requests.post(url, headers=headers, json=data, timeout=30)

        print("VISION:", res.text)

        if res.status_code == 200:
            return res.json()["choices"][0]["message"]["content"]

    except Exception as e:
        print("VISION ERROR:", e)

    return ""

# ===== TEXT AI =====
def generate_text(prompt):
    try:
        url = "https://api.aicredits.in/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {AICREDITS_KEY}",
            "Content-Type": "application/json"
        }

        data = {
            "model": "openai/gpt-4o-mini",
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        res = requests.post(url, headers=headers, json=data, timeout=30)

        if res.status_code == 200:
            return res.json()["choices"][0]["message"]["content"]

    except:
        pass

    return ""

# ===== PPT =====
async def make_ppt(update, questions, image_path=None):
    prs = Presentation()

    for i, q in enumerate(questions, 1):
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        # IMAGE LEFT
        if image_path and os.path.exists(image_path):
            slide.shapes.add_picture(image_path, Inches(0.5), Inches(1), width=Inches(5))

        # TEXT RIGHT
        box = slide.shapes.add_textbox(Inches(6), Inches(1), Inches(6), Inches(5))
        tf = box.text_frame
        tf.clear()
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

        p = tf.paragraphs[0]
        p.text = f"{i}. {q}"

    prs.save("output.pptx")

    with open("output.pptx", "rb") as f:
        await update.message.reply_document(InputFile(f))

    os.remove("output.pptx")

# ===== HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Image | ✍️ Text | 📄 PDF bhejo")

# TEXT
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = generate_text(update.message.text)

    if not res:
        await update.message.reply_text("❌ AI fail")
        return

    questions = extract_questions(res)
    await make_ppt(update, questions)

# IMAGE (VISION)
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()

    path = "img.jpg"
    await file.download_to_drive(path)

    res = generate_vision(path)

    if not res:
        await update.message.reply_text("❌ AI fail")
        return

    questions = extract_questions(res)

    await make_ppt(update, questions, image_path=path)

    os.remove(path)

# PDF
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    file = await doc.get_file()

    path = "file.pdf"
    await file.download_to_drive(path)

    text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t

    res = generate_text(text)

    if not res:
        await update.message.reply_text("❌ AI fail")
        return

    questions = extract_questions(res)

    await make_ppt(update, questions)

    os.remove(path)

# ===== MAIN =====
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))

    print("🚀 Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
