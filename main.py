import os
import re
from pptx import Presentation

from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ===== MCQ EXTRACT =====
def extract_mcq(text):
    pattern = r"(प्रश्न.*?A\).*?B\).*?C\).*?D\).*)"
    matches = re.findall(pattern, text, re.DOTALL)

    if not matches:
        # fallback english
        pattern = r"(Q\..*?A\).*?B\).*?C\).*?D\).*)"
        matches = re.findall(pattern, text, re.DOTALL)

    return matches

# ===== PPT =====
async def make_ppt(update, questions):
    prs = Presentation()

    if not questions:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = "No MCQ Found"
        slide.placeholders[1].text = "Text me MCQ nahi mila"
    else:
        for q in questions:
            lines = [l.strip() for l in q.split("\n") if l.strip()]

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

# ===== HANDLER =====
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    questions = extract_mcq(text)

    await make_ppt(update, questions)

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Text bhejo, MCQ PPT bana dunga")

# ===== MAIN =====
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
