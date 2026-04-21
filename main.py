import os
import re
import subprocess
import pdfplumber
import pytesseract
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


# ===== IMAGE ENHANCE =====
def enhance_image(img):
    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(2.5)
    img = img.filter(ImageFilter.SHARPEN)
    return img


# ===== CLEAN TEXT =====
def clean_text(text):
    lines = text.split("\n")
    clean = []

    for line in lines:
        line = line.strip()

        if not line:
            continue

        # remove WhatsApp timestamps
        if re.search(r"\[\d{1,2}/\d{1,2}", line):
            continue

        # remove short name tags like "Pratik Sir:"
        if ":" in line and len(line.split()) <= 4:
            continue

        clean.append(line)

    return "\n".join(clean)


# ===== UNIVERSAL MCQ EXTRACTOR =====
def extract_mcq(text):
    text = clean_text(text)
    lines = text.split("\n")

    questions = []
    current = []
    option_count = 0

    for line in lines:
        line = line.strip()

        if not line:
            continue

        # detect options (a) / a) / A. / (1)
        if re.match(r"^\(?[a-dA-D1-4][\)\.\-]", line):
            current.append(line)
            option_count += 1
            continue

        # अगर 2+ options मिल गए तो question complete
        if option_count >= 2:
            questions.append("\n".join(current))
            current = []
            option_count = 0

        current.append(line)

    # last question
    if current and option_count >= 2:
        questions.append("\n".join(current))

    return questions


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


# ===== PPT MAKER =====
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
            run.font.size = Pt(28)
            run.font.color.rgb = RGBColor(255, 255, 0)

    def style_option(p):
        for run in p.runs:
            run.font.size = Pt(26)
            run.font.color.rgb = RGBColor(255, 255, 255)

    if not questions:
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        set_black_background(slide)

        box = slide.shapes.add_textbox(Inches(3), Inches(3), Inches(8), Inches(1))
        tf = box.text_frame

        p = tf.paragraphs[0]
        p.text = "❌ No MCQ Found"
        style_question(p)

    else:
        for i, q in enumerate(questions, start=1):
            lines = [l.strip() for l in q.split("\n") if l.strip()]
            if not lines:
                continue

            slide = prs.slides.add_slide(prs.slide_layouts[6])
            set_black_background(slide)

            box = slide.shapes.add_textbox(Inches(2), Inches(1), Inches(10), Inches(5))
            tf = box.text_frame
            tf.clear()
            setup_tf(tf)

            # question
            p = tf.paragraphs[0]
            p.text = f"{i}. {lines[0]}"
            style_question(p)

            tf.add_paragraph().text = ""

            # options
            for opt in lines[1:]:
                p = tf.add_paragraph()
                p.text = opt
                style_option(p)

    ppt_file = "output.pptx"
    prs.save(ppt_file)

    pdf_file = convert_ppt_to_pdf(ppt_file)

    # send files
    with open(ppt_file, "rb") as f:
        await update.message.reply_document(InputFile(f))

    with open(pdf_file, "rb") as f:
        await update.message.reply_document(InputFile(f))

    os.remove(ppt_file)
    os.remove(pdf_file)


# ===== HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Image | ✍️ Text | 📄 PDF bhejo — MCQ PPT bana dunga")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    questions = extract_mcq(text)
    await make_ppt(update, questions)


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Processing image...")

    photo = update.message.photo[-1]
    file = await photo.get_file()

    path = "img.jpg"
    await file.download_to_drive(path)

    img = enhance_image(Image.open(path))
    text = pytesseract.image_to_string(img, lang="hin+eng")
    os.remove(path)

    if not text or len(text.strip()) < 20:
        await update.message.reply_text("❌ Text not detected")
        return

    questions = extract_mcq(text)
    await make_ppt(update, questions)


async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📄 Processing PDF...")

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

        # fallback OCR
        if len(all_text.strip()) < 50:
            all_text = ""
            for i in range(1, 50):
                images = convert_from_path(path, dpi=300, first_page=i, last_page=i)
                if not images:
                    break
                img = enhance_image(images[0])
                text = pytesseract.image_to_string(img, lang="hin+eng")
                if text:
                    all_text += text + "\n"

        questions = extract_mcq(all_text)
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
