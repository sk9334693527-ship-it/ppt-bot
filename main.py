import os
import re
import google.generativeai as genai
from groq import Groq
from PIL import Image, ImageEnhance, ImageFilter
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
    text = text.replace("\n\n\n", "\n\n")
    return text.strip()

# ===== IMAGE ENHANCE =====
def enhance_image(img):
    img = img.convert("L")  # grayscale
    img = ImageEnhance.Contrast(img).enhance(2.5)
    img = img.filter(ImageFilter.SHARPEN)
    return img

# ===== PROMPTS =====
STRICT_PROMPT = """
You are an OCR extraction engine.

ONLY copy text EXACTLY.

Extract MCQ questions.

FORMAT:

Question
A)
B)
C)
D)
"""

RELAX_PROMPT = """
Extract MCQ questions from image.

Keep same language.

FORMAT:
Question
A)
B)
C)
D)
"""

# ===== AI =====
def generate_ai(prompt, image=None):
    try:
        if image:
            res = gemini_model.generate_content([prompt, image])
        else:
            res = gemini_model.generate_content(prompt)
        return res.text
    except Exception as e:
        print("Gemini failed:", e)

    try:
        chat = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3-70b-8192"
        )
        return chat.choices[0].message.content
    except Exception as e:
        print("Groq failed:", e)

    return ""

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Image | ✍️ Text | 📄 PDF bhejo — PPT bana dunga")

# ===== IMAGE =====
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Image process ho rahi hai...")

    photo = update.message.photo[-1]
    file = await photo.get_file()

    path = "img.jpg"
    await file.download_to_drive(path)

    img = Image.open(path)
    img = enhance_image(img)

    data = generate_ai(STRICT_PROMPT, image=img)

    if not data or len(data.strip()) < 20:
        data = generate_ai(RELAX_PROMPT, image=img)

    os.remove(path)

    await make_ppt(update, clean(data))

# ===== TEXT =====
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = f"""
Convert into MCQ:

{update.message.text}
"""
    data = generate_ai(prompt)
    await make_ppt(update, clean(data))

# ===== PDF =====
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📄 PDF process ho raha hai...")

    doc = update.message.document
    file = await doc.get_file()

    path = "file.pdf"
    await file.download_to_drive(path)

    images = convert_from_path(path, dpi=300)  # HIGH DPI
    os.remove(path)

    if len(images) > 50:
        await update.message.reply_text("❌ Max 50 pages allowed")
        return

    prs = Presentation()

    for i, img in enumerate(images):
        await update.message.reply_text(f"⚙️ Page {i+1}")

        # enhance + crop
        img = enhance_image(img)

        w, h = img.size
        img = img.crop((0, 0, w, int(h * 0.7)))

        data = generate_ai(STRICT_PROMPT, image=img)

        if not data or len(data.strip()) < 20:
            data = generate_ai(RELAX_PROMPT, image=img)

        print("AI OUTPUT:", data[:300])

        if not data:
            slide = prs.slides.add_slide(prs.slide_layouts[1])
            slide.shapes.title.text = "❌ No Text"
            slide.placeholders[1].text = "AI failed"
            continue

        for block in data.split("\n\n"):
            lines = [l.strip() for l in block.split("\n") if l.strip()]

            if len(lines) < 2:
                slide = prs.slides.add_slide(prs.slide_layouts[1])
                slide.shapes.title.text = "⚠ Raw Text"
                slide.placeholders[1].text = block[:500]
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

# ===== PPT =====
async def make_ppt(update, data):
    prs = Presentation()

    if not data:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = "❌ No Data"
        slide.placeholders[1].text = "AI failed"
    else:
        for block in data.split("\n\n"):
            lines = [l.strip() for l in block.split("\n") if l.strip()]

            if len(lines) < 2:
                slide = prs.slides.add_slide(prs.slide_layouts[1])
                slide.shapes.title.text = "⚠ Raw"
                slide.placeholders[1].text = block[:500]
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
