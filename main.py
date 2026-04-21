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
    text = re.sub(r"\[.*?\]", "", text)
    text = re.sub(r".*?:", "", text)
    return text


# ===== NORMALIZE OPTIONS =====
def normalize(text):
    text = re.sub(r"\(\s*([a-dA-D])\s*\)", r"\1.", text)
    text = re.sub(r"\b([a-dA-D])\)", r"\1.", text)
    return text


# ===== MCQ EXTRACTOR =====
def extract_mcq(text):
    text = clean_text(text)
    text = normalize(text)

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    mcqs = []
    i = 0

    while i < len(lines):
        line = lines[i]

        if re.match(r"^[A-Da-d]\.", line):
            opts = []
            j = i

            while j < len(lines) and re.match(r"^[A-Da-d]\.", lines[j]):
                opts.append(lines[j])
                j += 1

            if len(opts) >= 2:
                q = []
                k = i - 1

                while k >= 0 and not re.match(r"^[A-Da-d]\.", lines[k]):
                    q.insert(0, lines[k])
                    k -= 1

                mcqs.append("\n".join(q + opts))

            i = j
        else:
            i += 1

    return mcqs


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
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = RGBColor(0, 0, 0)

    for i, q in enumerate(questions, 1):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        set_black_background(slide)

        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(11), Inches(5))
        tf = box.text_frame
        tf.clear()

        lines = q.split("\n")

        p = tf.paragraphs[0]
        p.text = f"{i}. " + lines[0]

        # बाकी question lines
        for line in lines[1:]:
            p = tf.add_paragraph()
            p.text = line

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
    await update.message.reply_text("Text / Image / PDF bhejo — MCQ PPT bana dunga")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    questions = extract_mcq(text)
    await make_ppt(update, questions)


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Processing image...")

    photo = update.message.photo[-1]
    file = await photo.get_file()

    path = "img.jpg"
    await file.download_to_drive(path)

    img = enhance_image(Image.open(path))
    text = pytesseract.image_to_string(img, lang="hin+eng")

    os.remove(path)

    questions = extract_mcq(text)
    await make_ppt(update, questions)


async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Processing PDF...")

    doc = update.message.document
    file = await doc.get_file()

    path = "file.pdf"
    await file.download_to_drive(path)

    all_text = ""

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                all_text += t + "\n"

    if len(all_text.strip()) < 50:
        for i in range(1, 20):
            images = convert_from_path(path, dpi=300, first_page=i, last_page=i)
            if not images:
                break
            img = enhance_image(images[0])
            t = pytesseract.image_to_string(img, lang="hin+eng")
            all_text += t + "\n"

    os.remove(path)

    questions = extract_mcq(all_text)
    await make_ppt(update, questions)


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
