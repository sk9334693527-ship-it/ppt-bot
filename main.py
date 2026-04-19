import os
import re
import pdfplumber
import pytesseract
import google.generativeai as genai
from groq import Groq
from PIL import Image, ImageEnhance, ImageFilter
from pdf2image import convert_from_path

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_AUTO_SIZE

from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ===== CONFIG =====
BOT_TOKEN = os.getenv("BOT_TOKEN")

GEMINI_KEYS = [
    os.getenv("GEMINI_API_KEY"),
    os.getenv("GEMINI_API_KEY1"),
    os.getenv("GEMINI_API_KEY2"),
    os.getenv("GEMINI_API_KEY3"),
]

GROQ_KEYS = [
    os.getenv("GROQ_API_KEY"),
    os.getenv("GROQ_API_KEY1"),
    os.getenv("GROQ_API_KEY2"),
]

GEMINI_KEYS = [k for k in GEMINI_KEYS if k]
GROQ_KEYS = [k for k in GROQ_KEYS if k]

# Gemini models
gemini_models = []
for key in GEMINI_KEYS:
    genai.configure(api_key=key)
    gemini_models.append(genai.GenerativeModel("gemini-2.5-flash"))

# Groq clients
groq_clients = [Groq(api_key=k) for k in GROQ_KEYS]

# ===== IMAGE ENHANCE =====
def enhance_image(img):
    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(2.5)
    img = img.filter(ImageFilter.SHARPEN)
    return img

# ===== AI =====
def generate_ai(prompt):
    for model in gemini_models:
        try:
            res = model.generate_content(prompt)
            if res.text:
                return res.text
        except:
            continue

    for client in groq_clients:
        try:
            chat = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama3-70b-8192"
            )
            return chat.choices[0].message.content
        except:
            continue

    return ""

# ===== PROMPT =====
FIX_PROMPT = """
तुम एक MCQ generator हो।

जरूरी नियम:
1. यूजर जितने प्रश्न मांगे उतने ही बनाओ
2. अगर संख्या नहीं दी है तो default 10 प्रश्न बनाओ
3. हर प्रश्न अलग होना चाहिए
4. हर प्रश्न में 4 विकल्प (A, B, C, D)
5. सही उत्तर भी दो

FORMAT STRICT:

प्रश्न ...
A)
B)
C)
D)
उत्तर: A

(इसी format में सारे प्रश्न)

कोई extra text नहीं देना।
"""

# ===== PPT =====
async def make_ppt(update, questions):
    prs = Presentation()
    prs.slide_width = Inches(13.33)
    prs.slide_height = Inches(7.5)

    def set_black_background(slide):
        bg = slide.background
        fill = bg.fill
        fill.solid()
        fill.fore_color.rgb = RGBColor(0, 0, 0)

    def setup_tf(tf):
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

    def style_question(p):
        for run in p.runs:
            run.font.size = Pt(24)
            run.font.color.rgb = RGBColor(255, 255, 0)

    def style_option(p):
        for run in p.runs:
            run.font.size = Pt(24)
            run.font.color.rgb = RGBColor(255, 255, 255)

    answers = []

    if not questions:
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        set_black_background(slide)

        box = slide.shapes.add_textbox(Inches(3.5), Inches(3), Inches(9), Inches(1))
        tf = box.text_frame
        setup_tf(tf)

        p = tf.paragraphs[0]
        p.text = "❌ No Data"
        style_question(p)

    else:
        for i, q in enumerate(questions, start=1):
            lines = [l.strip() for l in q.split("\n") if l.strip()]
            if not lines:
                continue

            slide = prs.slides.add_slide(prs.slide_layouts[6])
            set_black_background(slide)

            box = slide.shapes.add_textbox(Inches(3.5), Inches(1), Inches(9), Inches(5))
            tf = box.text_frame
            tf.clear()
            setup_tf(tf)

            question_text = re.sub(r"^प्रश्न\s*", "", lines[0])
            question_text = f"{i}. {question_text}"

            p = tf.paragraphs[0]
            p.text = question_text
            style_question(p)

            tf.add_paragraph().text = ""

            for line in lines[1:]:
                if line.startswith("उत्तर"):
                    ans = re.sub(r"उत्तर[:\s]*", "", line)
                    answers.append(f"{i}. {ans}")
                else:
                    p = tf.add_paragraph()
                    p.text = line
                    style_option(p)

    if answers:
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        set_black_background(slide)

        box = slide.shapes.add_textbox(Inches(3.5), Inches(1), Inches(9), Inches(5))
        tf = box.text_frame
        setup_tf(tf)

        p = tf.paragraphs[0]
        p.text = "Answers"
        style_question(p)

        for ans in answers:
            p = tf.add_paragraph()
            p.text = ans
            style_option(p)

    file = "output.pptx"
    prs.save(file)

    with open(file, "rb") as f:
        await update.message.reply_document(InputFile(f))

    os.remove(file)

# ===== HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Image | ✍️ Text | 📄 PDF bhejo — PPT bana dunga")

# ✅ FIXED PART ONLY HERE
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    match = re.search(r"(\d+)", text)
    count = match.group(1) if match else "10"

    fixed_prompt = f"""
{FIX_PROMPT}

कुल {count} प्रश्न बनाओ

TEXT:
{text}
"""

    fixed = generate_ai(fixed_prompt)

    if not fixed:
        await update.message.reply_text("❌ AI fail ho gaya")
        return

    questions = re.split(r"\n(?=प्रश्न)", fixed)
    await make_ppt(update, questions)

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

    fixed = generate_ai(FIX_PROMPT + "\nTEXT:\n" + text)

    if not fixed:
        await update.message.reply_text("❌ AI fail ho gaya")
        return

    questions = re.split(r"\n(?=प्रश्न)", fixed)
    await make_ppt(update, questions)

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📄 PDF process ho raha hai...")

    doc = update.message.document
    file = await doc.get_file()

    path = "file.pdf"
    await file.download_to_drive(path)

    try:
        all_text = ""

        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    all_text += text + "\n"

        if len(all_text.strip()) > 50:
            fixed = generate_ai(FIX_PROMPT + "\nTEXT:\n" + all_text)
        else:
            all_text = ""
            for i in range(1, 50):
                images = convert_from_path(path, dpi=300, first_page=i, last_page=i)
                if not images:
                    break
                img = enhance_image(images[0])
                text = pytesseract.image_to_string(img, lang="hin+eng")
                if text:
                    all_text += text + "\n"

            fixed = generate_ai(FIX_PROMPT + "\nTEXT:\n" + all_text)

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
