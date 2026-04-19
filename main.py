import os
import re
from pptx import Presentation

from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ===== SUPER SMART MCQ EXTRACT =====
def extract_mcq(text):

    # normalize text
    text = text.replace("\r", "")

    pattern = r"""
    (
        (?:Q\.?\s*\d+|प्रश्न\s*\d+|\d+\.)     # question start
        [\s\S]*?                             # question body
        (?:A[\.\)\:]\s*[\s\S]*?)
        (?:B[\.\)\:]\s*[\s\S]*?)
        (?:C[\.\)\:]\s*[\s\S]*?)
        (?:D[\.\)\:]\s*[\s\S]*?)
    )
    """

    matches = re.findall(pattern, text, re.VERBOSE)

    return matches

# ===== CLEAN LINES =====
def clean_lines(q):
    lines = [l.strip() for l in q.split("\n") if l.strip()]
    return lines

# ===== PPT =====
async def make_ppt(update, questions):
    prs = Presentation()

    if not questions:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = "❌ No MCQ Found"
        slide.placeholders[1].text = "Text me MCQ nahi mila"
    else:
        for q in questions:
            lines = clean_lines(q)

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

    print("==== TEXT RECEIVED ====")
    print(text[:500])

    questions = extract_mcq(text)

    print("==== MCQ FOUND ====", len(questions))

    for i, q in enumerate(questions[:3]):
        print(f"\nMCQ {i+1}:\n{q}\n")

    await make_ppt(update, questions)

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📄 Text bhejo, MCQ PPT bana dunga")

# ===== MAIN =====
def main():
    print("🚀 Bot Started")

    if not BOT_TOKEN:
        print("❌ BOT_TOKEN missing")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
