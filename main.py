import os
import re
import pdfplumber
import pytesseract
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
def generate_ai(prompt):
    try:
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

# ===== HINDI FIX =====
FIX_PROMPT = """
तुम एक हिंदी टेक्स्ट करेक्शन इंजन हो।

RULES:
1. केवल मात्रा सुधारो (ा ि ी ु ू े ै ो ौ)
2. शब्द मत बदलो
3. भाषा मत बदलो
4. नया कुछ मत जोड़ो

फिर MCQ format में बदलो:

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

    text = pytesseract.image_to_string(img, lang="hin+eng")

    fixed = generate_ai(FIX_PROMPT + text)

    os.remove(path)

    questions = fixed.split("\n\n")
    await make_ppt(update, questions)

# ===== PDF =====
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📄 PDF process ho raha hai...")

    doc = update.message.document
    file = await doc.get_file()

    path = "file.pdf"
    await file.download_to_drive(path)

    questions = []

    try:
        # ===== TEXT PDF =====
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages):
                await update.message.reply_text(f"📄 Page {i+1} read ho raha hai...")

                text = page.extract_text()

                if text and len(text.strip()) > 20:
                    fixed = generate_ai(FIX_PROMPT + text)
                    if fixed:
                        questions.extend(fixed.split("\n\n"))

        # ===== अगर मिला =====
        if questions:
            os.remove(path)
            await make_ppt(update, questions)
            return

        # ===== OCR FALLBACK =====
        await update.message.reply_text("⚠ Scanned PDF detect hua — OCR chal raha hai...")

        for i in range(1, 30):
            await update.message.reply_text(f"📄 Page {i} OCR...")

            images = convert_from_path(path, dpi=300, first_page=i, last_page=i)
            if not images:
                break

            img = enhance_image(images[0])

            text = pytesseract.image_to_string(img, lang="hin+eng")

            if text and len(text.strip()) > 20:
                fixed = generate_ai(FIX_PROMPT + text)
                if fixed:
                    questions.extend(fixed.split("\n\n"))

        os.remove(path)

        if not questions:
            await update.message.reply_text("❌ Kuch bhi extract nahi ho paya (PDF quality low hai)")
            return

        await make_ppt(update, questions)

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
