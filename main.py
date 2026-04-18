import os
import re
import pdfplumber
import google.generativeai as genai
from PIL import Image

from pptx import Presentation
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ===== CONFIG =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# ===== CLEAN =====
def clean(text):
    text = re.sub(r"\*\*", "", text)
    return text.strip()

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Image | ✍️ Text | 📄 PDF bhejo — main PPT bana dunga")

# ===== IMAGE =====
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Image process ho rahi hai...")

    photo = update.message.photo[-1]
    file = await photo.get_file()

    path = "img.jpg"
    await file.download_to_drive(path)

    img = Image.open(path)

    prompt = """
Image me jo question hai use EXACT same likho.
Language change mat karo.

MCQ format me convert karo:

Question
A)
B)
C)
D)

No explanation.
"""

    response = model.generate_content([prompt, img])
    os.remove(path)

    await make_ppt(update, clean(response.text))

# ===== TEXT =====
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    await update.message.reply_text("✍️ Text process ho raha hai...")

    prompt = f"""
Question ko EXACT same rakho.
Language same rakho.

MCQ format:

Question
A)
B)
C)
D)

TEXT:
{user_text}
"""

    response = model.generate_content(prompt)

    await make_ppt(update, clean(response.text))

# ===== PDF =====
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📄 PDF process ho raha hai...")

    doc = update.message.document
    file = await doc.get_file()

    path = "file.pdf"
    await file.download_to_drive(path)

    text = ""

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"

    os.remove(path)

    if not text.strip():
        await update.message.reply_text("❌ PDF se text nahi mila")
        return

    # limit (AI crash avoid)
    text = text[:8000]

    prompt = f"""
Is text me se MCQ questions nikaalo.

RULES:
- Question same rakho
- Language same rakho
- Sirf MCQ format

FORMAT:
Question
A)
B)
C)
D)

TEXT:
{text}
"""

    response = model.generate_content(prompt)

    await make_ppt(update, clean(response.text))

# ===== PPT =====
async def make_ppt(update, data):
    prs = Presentation()

    for block in data.split("\n\n"):
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if len(lines) < 2:
            continue

        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = lines[0]

        tf = slide.placeholders[1].text_frame
        tf.text = ""

        for l in lines[1:]:
            tf.add_paragraph().text = l

    file = "output.pptx"
    prs.save(file)

    with open(file, "rb") as f:
        await update.message.reply_document(InputFile(f))

    os.remove(file)

# ===== MAIN =====
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))

    print("🚀 Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
