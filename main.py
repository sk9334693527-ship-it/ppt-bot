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

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# Railway OCR path
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

# ================= CLEAN =================
def clean_text(text):
    text = re.sub(r"\*\*", "", text)
    text = re.sub(r"`", "", text)
    text = re.sub(r"Explanation.*", "", text, flags=re.DOTALL)
    return text.strip()

# ================= MATH =================
def format_math(text):
    text = re.sub(r"sqrt\((.*?)\)", r"√\1", text)
    text = re.sub(r"(\d+)\^2", r"\1²", text)
    text = text.replace("/", "⁄")
    return text

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Image bhejo (Hindi/English), main SAME question ke sath PPT bana dunga!")

# ================= IMAGE HANDLER =================
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Image process ho raha hai...")

    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()

        file_path = "input.jpg"
        await file.download_to_drive(file_path)

        img = Image.open(file_path).convert("L")

        # OCR
        extracted_text = pytesseract.image_to_string(img, config='--oem 3 --psm 6')

        os.remove(file_path)

        if not extracted_text.strip():
            await update.message.reply_text("❌ OCR me text nahi mila")
            return

        await process_input(update, context, extracted_text)

    except Exception as e:
        await update.message.reply_text(f"❌ IMAGE ERROR:\n{str(e)}")

# ================= PROCESS =================
async def process_input(update, context, user_text):
    await update.message.reply_text("🤖 MCQ bana raha hu (same question)...")

    prompt = f"""
STRICT RULES (Follow 100%):

1. Question ko EXACT same rakho (ek bhi word change mat karo)
2. Language same rakho (Hindi → Hindi, English → English)
3. Sirf MCQ format me convert karo
4. Agar options already hain → same use karo
5. Agar options nahi hain → new options bana sakte ho
6. Koi explanation nahi dena
7. Question ko modify, short ya rewrite mat karo

FORMAT:

Question (same as input)
A)
B)
C)
D)

TEXT:
{user_text}
"""

    try:
        response = model.generate_content(prompt)
        data = clean_text(response.text)

    except Exception as e:
        await update.message.reply_text(f"❌ GEMINI ERROR:\n{str(e)}")
        return

    # ===== PPT =====
    try:
        questions = [q.strip() for q in data.split("\n\n") if q.strip()]

        prs = Presentation()
        prs.slide_width = Inches(13.33)
        prs.slide_height = Inches(7.5)

        for q in questions:
            lines = [format_math(l.strip()) for l in q.split("\n") if l.strip()]

            if len(lines) < 2:
                continue

            slide = prs.slides.add_slide(prs.slide_layouts[6])

            # background black
            bg = slide.background.fill
            bg.solid()
            bg.fore_color.rgb = RGBColor(0, 0, 0)

            box = slide.shapes.add_textbox(Inches(2), Inches(1), Inches(10), Inches(5))
            tf = box.text_frame

            # Question
            p = tf.paragraphs[0]
            p.text = lines[0]
            p.font.size = Pt(32)
            p.font.bold = True
            p.font.color.rgb = RGBColor(255, 255, 0)

            # Options
            for l in lines[1:]:
                p = tf.add_paragraph()
                p.text = l
                p.font.size = Pt(26)
                p.font.color.rgb = RGBColor(255, 255, 255)

        file_name = "final.pptx"
        prs.save(file_name)

        with open(file_name, "rb") as f:
            await update.message.reply_document(InputFile(f))

        os.remove(file_name)

    except Exception as e:
        await update.message.reply_text(f"❌ PPT ERROR:\n{str(e)}")

# ================= MAIN =================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))

    print("🚀 Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
