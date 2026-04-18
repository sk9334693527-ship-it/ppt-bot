import os
import re
import pytesseract
from PIL import Image, ImageEnhance

import google.generativeai as genai

from pptx import Presentation
from pptx.util import Inches

from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

# ================= OCR IMPROVE =================
def preprocess_image(img):
    img = img.convert("L")

    # contrast increase
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2)

    # sharpness increase
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(2)

    # resize
    img = img.resize((img.width * 2, img.height * 2))

    return img

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Image ya text bhejo — main PPT bana dunga!")

# ================= IMAGE =================
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Image process ho raha hai...")

    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()

        file_path = "input.jpg"
        await file.download_to_drive(file_path)

        img = Image.open(file_path)
        img = preprocess_image(img)

        text = pytesseract.image_to_string(
            img,
            config='--oem 3 --psm 6 -l eng+hin'
        )

        os.remove(file_path)

        if not text.strip():
            await update.message.reply_text("❌ OCR fail ho gaya")
            return

        # DEBUG
        await update.message.reply_text("🧾 OCR:\n" + text[:500])

        await make_ppt(update, text)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

# ================= TEXT =================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await make_ppt(update, update.message.text)

# ================= AI =================
def format_text(text):
    text = re.sub(r"\*\*", "", text)
    return text.strip()

async def make_ppt(update, text):
    await update.message.reply_text("🤖 PPT bana raha hu...")

    prompt = f"""
TEXT ko MCQ format me convert karo.

RULES:
- Question ko same rakho
- Language same rakho
- Sirf format karo
- No explanation

TEXT:
{text}
"""

    try:
        response = model.generate_content(prompt)
        data = format_text(response.text)
    except Exception as e:
        await update.message.reply_text(f"❌ AI Error: {str(e)}")
        return

    # PPT
    prs = Presentation()

    for block in data.split("\n\n"):
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if len(lines) < 2:
            continue

        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = lines[0]

        content = slide.placeholders[1].text_frame
        content.text = ""

        for l in lines[1:]:
            content.add_paragraph().text = l

    file = "output.pptx"
    prs.save(file)

    with open(file, "rb") as f:
        await update.message.reply_document(InputFile(f))

    os.remove(file)

# ================= MAIN =================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🚀 Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
