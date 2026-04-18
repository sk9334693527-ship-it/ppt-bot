import os
import re
import google.generativeai as genai
from groq import Groq
from PIL import Image
from pdf2image import convert_from_path

from pptx import Presentation
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ===== CONFIG =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.5-flash")

groq_client = Groq(api_key=GROQ_API_KEY)

# ===== CLEAN =====
def clean(text):
    text = re.sub(r"\*\*", "", text)
    return text.strip()

# ===== AI FALLBACK =====
def generate_ai(prompt, image=None):
    # ===== GEMINI =====
    try:
        if image:
            res = gemini_model.generate_content([prompt, image])
        else:
            res = gemini_model.generate_content(prompt)
        return res.text
    except Exception as e:
        print("Gemini failed:", e)

    # ===== GROQ =====
    try:
        chat = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3-70b-8192"
        )
        return chat.choices[0].message.content
    except Exception as e:
        print("Groq failed:", e)

    return "❌ AI Failed"

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 Image | ✍️ Text | 📄 PDF bhejo — main PPT bana dunga"
    )

# ===== IMAGE =====
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Image process ho rahi hai...")

    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()

        path = "img.jpg"
        await file.download_to_drive(path)

        img = Image.open(path)

        prompt = """
Image me jo question hai use EXACT same likho.
Language change mat karo.

MCQ format:

Question
A)
B)
C)
D)
"""

        data = generate_ai(prompt, image=img)
        os.remove(path)

        await make_ppt(update, clean(data))

    except Exception as e:
        await update.message.reply_text(f"❌ IMAGE ERROR:\n{str(e)}")

# ===== TEXT =====
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
{update.message.text}
"""

    data = generate_ai(prompt)
    await make_ppt(update, clean(data))

# ===== PDF =====
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📄 PDF process ho raha hai...")

    try:
        doc = update.message.document
        file = await doc.get_file()

        path = "file.pdf"
        await file.download_to_drive(path)

        images = convert_from_path(path, dpi=150)
        os.remove(path)

        total = len(images)

        if total > 50:
            await update.message.reply_text("❌ Max 50 pages allowed")
            return

        prs = Presentation()

        batch_size = 2

        for i in range(0, total, batch_size):
            batch = images[i:i+batch_size]
            await update.message.reply_text(f"⚙️ Pages {i+1}-{i+len(batch)}")

            for img in batch:
                prompt = """
MCQ questions EXACT same likho.

FORMAT:
Question
A)
B)
C)
D)
"""
                data = generate_ai(prompt, image=img)

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

        file_name = "output.pptx"
        prs.save(file_name)

        with open(file_name, "rb") as f:
            await update.message.reply_document(InputFile(f))

        os.remove(file_name)

    except Exception as e:
        await update.message.reply_text(f"❌ PDF ERROR:\n{str(e)}")

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
