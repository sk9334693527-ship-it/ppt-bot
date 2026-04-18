import os
import re
import google.generativeai as genai
from PIL import Image
from pdf2image import convert_from_path

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

Usko MCQ format me convert karo:

Question
A)
B)
C)
D)

No explanation.
"""

        response = model.generate_content([prompt, img])
        data = clean(response.text)

        os.remove(path)

        await make_ppt(update, data)

    except Exception as e:
        await update.message.reply_text(f"❌ IMAGE ERROR:\n{str(e)}")

# ===== TEXT =====
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    await update.message.reply_text("✍️ Text process ho raha hai...")

    prompt = f"""
STRICT RULES:

1. Question ko EXACT same rakho
2. Language same rakho
3. Sirf MCQ format me convert karo
4. No explanation

FORMAT:

Question
A)
B)
C)
D)

TEXT:
{user_text}
"""

    try:
        response = model.generate_content(prompt)
        data = clean(response.text)

        await make_ppt(update, data)

    except Exception as e:
        await update.message.reply_text(f"❌ TEXT ERROR:\n{str(e)}")

# ===== PDF (LARGE SAFE VERSION) =====
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📄 PDF process ho raha hai... ⏳")

    try:
        doc = update.message.document
        file = await doc.get_file()

        path = "file.pdf"
        await file.download_to_drive(path)

        # convert PDF → images (LOW DPI for memory safety)
        images = convert_from_path(path, dpi=150)

        os.remove(path)

        total_pages = len(images)

        # SAFETY LIMIT
        if total_pages > 50:
            await update.message.reply_text("❌ PDF bahut bada hai (max 50 pages allowed)")
            return

        await update.message.reply_text(f"📊 Total pages: {total_pages}")

        prs = Presentation()

        batch_size = 2  # VERY IMPORTANT (memory safe)

        for i in range(0, total_pages, batch_size):
            batch = images[i:i+batch_size]

            await update.message.reply_text(f"⚙️ Pages {i+1} to {i+len(batch)} process ho rahe hain...")

            for img in batch:
                prompt = """
Is image me jo MCQ questions hain unhe EXACT same likho.

RULES:
- Question change mat karo
- Language same rakho
- Sirf MCQ format
- No explanation

FORMAT:

Question
A)
B)
C)
D)
"""

                response = model.generate_content([prompt, img])
                data = response.text

                # ===== ADD TO PPT =====
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

        await update.message.reply_text("✅ PDF convert ho gaya!")

    except Exception as e:
        await update.message.reply_text(f"❌ PDF ERROR:\n{str(e)}")

# ===== PPT FUNCTION =====
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
