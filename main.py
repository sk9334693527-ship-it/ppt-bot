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

# MULTI API KEYS
GEMINI_KEYS = os.getenv("GEMINI_KEYS", "").split(",")
GROQ_KEYS = os.getenv("GROQ_KEYS", "").split(",")

gemini_index = 0
groq_index = 0

# ===== IMAGE ENHANCE =====
def enhance_image(img):
    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(2.5)
    img = img.filter(ImageFilter.SHARPEN)
    return img

# ===== AI (MULTI KEY ROTATION) =====
def generate_ai(prompt):
    global gemini_index, groq_index

    # ===== GEMINI ROTATION =====
    if GEMINI_KEYS and GEMINI_KEYS != ['']:
        for _ in range(len(GEMINI_KEYS)):
            try:
                key = GEMINI_KEYS[gemini_index].strip()
                genai.configure(api_key=key)

                model = genai.GenerativeModel("gemini-2.5-flash")
                res = model.generate_content(prompt)

                gemini_index = (gemini_index + 1) % len(GEMINI_KEYS)
                return res.text

            except Exception:
                gemini_index = (gemini_index + 1) % len(GEMINI_KEYS)

    # ===== GROQ ROTATION =====
    if GROQ_KEYS and GROQ_KEYS != ['']:
        for _ in range(len(GROQ_KEYS)):
            try:
                key = GROQ_KEYS[groq_index].strip()
                client = Groq(api_key=key)

                chat = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama3-70b-8192"
                )

                groq_index = (groq_index + 1) % len(GROQ_KEYS)
                return chat.choices[0].message.content

            except Exception:
                groq_index = (groq_index + 1) % len(GROQ_KEYS)

    return ""

# ===== PROMPT =====
FIX_PROMPT = """
तुम एक हिंदी MCQ generator हो।

काम:
1. दिए गए टेक्स्ट से केवल प्रश्न निकालो
2. मात्रा की गलती सुधारो
3. प्रश्न का अर्थ मत बदलो
4. MCQ format में बदलो

FORMAT STRICT:
प्रश्न ...
A)
B)
C)
D)

कोई extra text नहीं देना।

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

    if not fixed:
        await update.message.reply_text("❌ AI fail ho gaya")
        return

    questions = re.split(r"\n(?=प्रश्न)", fixed)

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

    os.remove(path)

    if not text or len(text.strip()) < 20:
        await update.message.reply_text("❌ Image se text sahi nahi nikla")
        return

    await update.message.reply_text("🧠 AI pura text process kar raha hai...")

    fixed = generate_ai(FIX_PROMPT + text)

    if not fixed:
        await update.message.reply_text("❌ AI fail ho gaya")
        return

    questions = re.split(r"\n(?=प्रश्न)", fixed)

    await make_ppt(update, questions)

# ===== PDF =====
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📄 PDF process ho raha hai...")

    doc = update.message.document
    file = await doc.get_file()

    path = "file.pdf"
    await file.download_to_drive(path)

    try:
        all_text = ""

        # TEXT PDF
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages):
                await update.message.reply_text(f"📄 Page {i+1} read ho raha hai...")
                text = page.extract_text()
                if text:
                    all_text += text + "\n"

        if len(all_text.strip()) > 50:
            await update.message.reply_text("🧠 AI full PDF process kar raha hai...")

            fixed = generate_ai(FIX_PROMPT + all_text)

            if not fixed:
                await update.message.reply_text("❌ AI fail ho gaya")
                return

            questions = re.split(r"\n(?=प्रश्न)", fixed)

            os.remove(path)
            await make_ppt(update, questions)
            return

        # OCR fallback
        await update.message.reply_text("⚠ Scanned PDF detect hua — OCR chal raha hai...")

        all_text = ""

        for i in range(1, 50):
            await update.message.reply_text(f"📄 Page {i} OCR...")

            images = convert_from_path(path, dpi=300, first_page=i, last_page=i)
            if not images:
                break

            img = enhance_image(images[0])
            text = pytesseract.image_to_string(img, lang="hin+eng")

            if text:
                all_text += text + "\n"

        if len(all_text.strip()) < 20:
            await update.message.reply_text("❌ Kuch bhi extract nahi ho paya")
            os.remove(path)
            return

        await update.message.reply_text("🧠 OCR text AI ko bheja ja raha hai...")

        fixed = generate_ai(FIX_PROMPT + all_text)

        if not fixed:
            await update.message.reply_text("❌ AI fail ho gaya")
            os.remove(path)
            return

        questions = re.split(r"\n(?=प्रश्न)", fixed)

        os.remove(path)
        await make_ppt(update, questions)

    except Exception as e:
        await update.message.reply_text(f"❌ ERROR: {str(e)}")
        if os.path.exists(path):
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
