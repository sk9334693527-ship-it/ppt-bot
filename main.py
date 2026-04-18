import os
import re
import pdfplumber
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

# ===== IMAGE ENHANCE =====
def enhance_image(img):
    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(2.5)
    img = img.filter(ImageFilter.SHARPEN)
    return img

# ===== AI =====
def generate_ai(prompt, image=None):
    try:
        if image:
            res = gemini_model.generate_content([prompt, image])
        else:
            res = gemini_model.generate_content(prompt)
        return res.text
    except:
        try:
            chat = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama3-70b-8192"
            )
            return chat.choices[0].message.content
        except:
            return ""

# ===== HINDI FIX PROMPT =====
FIX_PROMPT = """
तुम एक हिंदी टेक्स्ट करेक्शन इंजन हो।

RULES:
1. केवल मात्रा (ा ि ी ु ू े ै ो ौ) सुधारो
2. शब्द मत बदलो
3. भाषा मत बदलो
4. नया कुछ मत जोड़ो

फिर उसे MCQ format में convert करो:

FORMAT:

प्रश्न
A)
B)
C)
D)

TEXT:
"""

# ===== PPT =====
async def make_ppt(update, questions):
    prs = Presentation()

    if not questions:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = "❌ No Data"
        slide.placeholders[1].text = "कुछ भी extract नहीं हुआ"
    else:
        for q in questions:
            lines = [l.strip() for l in q.split("\n") if l.strip()]
            if not lines:
                continue

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

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Image | ✍️ Text | 📄 PDF bhejo — PPT bana dunga")

# ===== TEXT =====
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    fixed = generate_ai(FIX_PROMPT + text)
    questions = fixed.split("\n\n")
    await make_ppt(update, questions)

# ===== IMAGE =====
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Image process ho rahi hai...")

    photo = update.message.photo[-1]
    file = await photo.get_file()

    path = "img.jpg"
    await file.download_to_drive(path)

    img = enhance_image(Image.open(path))

    data = generate_ai("Extract MCQ questions", image=img)
    os.remove(path)

    questions = data.split("\n\n")
    await make_ppt(update, questions)

# ===== PDF =====
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📄 PDF process ho raha hai...")

    doc = update.message.document
    file = await doc.get_file()

    path = "file.pdf"
    await file.download_to_drive(path)

    prs_questions = []

    try:
        # ===== TEXT EXTRACTION =====
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages):
                await update.message.reply_text(f"📄 Page {i+1} read ho raha hai...")

                text = page.extract_text()

                if text:
                    # large text safe
                    if len(text) > 3000:
                        text = text[:3000]

                    fixed = generate_ai(FIX_PROMPT + text)

                    if fixed:
                        qs = fixed.split("\n\n")
                        prs_questions.extend(qs)

        # ===== अगर text मिला =====
        if prs_questions:
            os.remove(path)
            await make_ppt(update, prs_questions)
            return

        # ===== FALLBACK (SCANNED PDF) =====
        await update.message.reply_text("⚠ Scanned PDF detected... AI use ho raha hai")

        for i in range(1, 30):
            await update.message.reply_text(f"📄 Page {i} processing...")

            images = convert_from_path(path, dpi=220, first_page=i, last_page=i)
            if not images:
                break

            img = enhance_image(images[0])

            data = generate_ai("Extract MCQ questions", image=img)

            if data:
                prs_questions.extend(data.split("\n\n"))

        os.remove(path)
        await make_ppt(update, prs_questions)

    except Exception as e:
        await update.message.reply_text(f"❌ ERROR: {str(e)}")
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
