import os
import re
import subprocess
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
]

GROQ_KEYS = [
    os.getenv("GROQ_API_KEY"),
    os.getenv("GROQ_API_KEY1"),
]

GEMINI_KEYS = [k for k in GEMINI_KEYS if k]
GROQ_KEYS = [k for k in GROQ_KEYS if k]

# ===== AI SETUP =====
gemini_models = []
for key in GEMINI_KEYS:
    genai.configure(api_key=key)
    gemini_models.append(genai.GenerativeModel("gemini-2.5-flash"))

groq_clients = [Groq(api_key=k) for k in GROQ_KEYS]

# ===== IMAGE ENHANCE =====
def enhance_image(img):
    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(2.5)
    img = img.filter(ImageFilter.SHARPEN)
    return img

# ===== AI CALL =====
def generate_ai(prompt):
    prompt = prompt[:12000]

    for _ in range(3):
        for model in gemini_models:
            try:
                res = model.generate_content(prompt)
                if res.text and len(res.text.strip()) > 20:
                    return res.text
            except:
                continue

        for client in groq_clients:
            try:
                chat = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama3-70b-8192"
                )
                text = chat.choices[0].message.content
                if text and len(text.strip()) > 20:
                    return text
            except:
                continue

    return ""

# ===== LARGE TEXT PROCESS =====
def process_large_text(text):
    text = re.sub(r'\s+', ' ', text)

    chunk_size = 3000
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

    final_output = ""

    for chunk in chunks[:6]:
        result = generate_ai(FIX_PROMPT + chunk)
        if result:
            final_output += result + "\n"

    return final_output

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

# ===== PPT → PDF =====
def convert_ppt_to_pdf(ppt_path):
    subprocess.run([
        "libreoffice",
        "--headless",
        "--convert-to", "pdf",
        "--outdir", ".",
        ppt_path
    ], check=True)

    return ppt_path.replace(".pptx", ".pdf")

# ===== PPT GENERATE =====
async def make_ppt(update, questions):
    prs = Presentation()
    prs.slide_width = Inches(13.33)
    prs.slide_height = Inches(7.5)

    def set_bg(slide):
        bg = slide.background
        fill = bg.fill
        fill.solid()
        fill.fore_color.rgb = RGBColor(0, 0, 0)

    def setup(tf):
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

    def style_q(p):
        for run in p.runs:
            run.font.size = Pt(24)
            run.font.color.rgb = RGBColor(255, 255, 0)

    def style_o(p):
        for run in p.runs:
            run.font.size = Pt(24)
            run.font.color.rgb = RGBColor(255, 255, 255)

    for i, q in enumerate(questions, start=1):
        lines = [l.strip() for l in q.split("\n") if l.strip()]
        if not lines:
            continue

        slide = prs.slides.add_slide(prs.slide_layouts[6])
        set_bg(slide)

        box = slide.shapes.add_textbox(Inches(3.5), Inches(1), Inches(9), Inches(5))
        tf = box.text_frame
        tf.clear()
        setup(tf)

        question = re.sub(r"^प्रश्न\s*", "", lines[0])
        p = tf.paragraphs[0]
        p.text = f"{i}. {question}"
        style_q(p)

        tf.add_paragraph().text = ""

        for opt in lines[1:]:
            p = tf.add_paragraph()
            p.text = opt
            style_o(p)

    ppt_file = "output.pptx"
    prs.save(ppt_file)

    pdf_file = convert_ppt_to_pdf(ppt_file)

    with open(ppt_file, "rb") as f:
        await update.message.reply_document(InputFile(f))

    with open(pdf_file, "rb") as f:
        await update.message.reply_document(InputFile(f))

    os.remove(ppt_file)
    os.remove(pdf_file)

# ===== HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📄 PDF / 📸 Image / ✍️ Text bhejo — PPT + PDF bana dunga")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fixed = process_large_text(update.message.text)

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

    if len(text.strip()) < 20:
        await update.message.reply_text("❌ Text nahi nikla")
        return

    fixed = process_large_text(text)

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
                t = page.extract_text()
                if t:
                    all_text += t + "\n"

        if len(all_text.strip()) < 100:
            images = convert_from_path(path, dpi=300)
            for img in images:
                img = enhance_image(img)
                t = pytesseract.image_to_string(img, lang="hin+eng")
                if t:
                    all_text += t + "\n"

        if len(all_text.strip()) < 50:
            await update.message.reply_text("❌ PDF se text nahi nikla")
            return

        fixed = process_large_text(all_text)

        if not fixed:
            await update.message.reply_text("❌ AI fail ho gaya")
            return

        questions = re.split(r"\n(?=प्रश्न)", fixed)
        await make_ppt(update, questions)

    except Exception as e:
        await update.message.reply_text(f"❌ ERROR: {str(e)}")

    finally:
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
