import os
import re
import google.generativeai as genai
from PIL import Image
import pytesseract

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

def clean_text(text):
    text = re.sub(r"\*\*", "", text)
    text = re.sub(r"`", "", text)
    return text.strip()

def format_math(text):
    text = re.sub(r"sqrt\((.*?)\)", r"√\1", text)
    text = text.replace("/", "⁄")
    return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Image bhejo, main PPT bana dunga!")

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Image process ho raha hai...")

    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()

        file_path = "input.jpg"
        await file.download_to_drive(file_path)

        img = Image.open(file_path).convert("L")

        text = pytesseract.image_to_string(img)

        os.remove(file_path)

        if not text.strip():
            await update.message.reply_text("❌ OCR fail ho gaya")
            return

        await process_text(update, context, text)

    except Exception as e:
        await update.message.reply_text(f"❌ Image Error: {str(e)}")

async def process_text(update, context, text):
    await update.message.reply_text("🤖 MCQ bana raha hu...")

    prompt = f"""
Convert this into MCQ format:

{text}

Format:
Question
A)
B)
C)
D)

No explanation
"""

    try:
        response = model.generate_content(prompt)
        data = clean_text(response.text)

        prs = Presentation()

        for q in data.split("\n\n"):
            lines = [format_math(x.strip()) for x in q.split("\n") if x.strip()]
            if len(lines) < 2:
                continue

            slide = prs.slides.add_slide(prs.slide_layouts[6])

            box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(5))
            tf = box.text_frame

            tf.text = lines[0]

            for l in lines[1:]:
                tf.add_paragraph().text = l

        file = "output.pptx"
        prs.save(file)

        with open(file, "rb") as f:
            await update.message.reply_document(InputFile(f))

        os.remove(file)

    except Exception as e:
        await update.message.reply_text(f"❌ AI Error: {str(e)}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
