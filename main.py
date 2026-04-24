import os
import re
import subprocess
import pdfplumber
import pytesseract
import google.generativeai as genai
from groq import Groq
import requests

from PIL import Image, ImageEnhance, ImageFilter
from pdf2image import convert_from_path

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_AUTO_SIZE

from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

import firebase_admin
from firebase_admin import credentials, firestore
import json

firebase_json = os.getenv("FIREBASE_CREDENTIALS")
cred = credentials.Certificate(json.loads(firebase_json))
firebase_admin.initialize_app(cred)
db = firestore.client()

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CONTACT_NUMBER = os.getenv("CONTACT_NUMBER", "XXXXXXXXXX")

admin_sessions = set()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ===== USER SAVE =====
def save_user(user):
    ref = db.collection("users").document(str(user.id))
    doc = ref.get()

    if not doc.exists:
        ref.set({
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "credits": 0
        })
    else:
        ref.set({
            "username": user.username,
            "first_name": user.first_name
        }, merge=True)

# ===== CREDIT =====
def get_user_credit(user_id):
    doc = db.collection("users").document(str(user_id)).get()
    if doc.exists:
        return doc.to_dict().get("credits", 0)
    return 0

def update_user_credit(user_id, amount):
    db.collection("users").document(str(user_id)).update({"credits": amount})

# ===== AI =====
def generate_ai(prompt):
    try:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel("gemini-2.5-flash")
        res = model.generate_content(prompt)
        return res.text
    except:
        return ""

FIX_PROMPT = "MCQ generate karo:\n"

# ===== PPT =====
async def make_ppt(update, questions):
    prs = Presentation()

    for i, q in enumerate(questions, start=1):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(5))
        tf = box.text_frame
        tf.text = q

    ppt_file = "output.pptx"
    prs.save(ppt_file)

    with open(ppt_file, "rb") as f:
        await update.message.reply_document(InputFile(f))

    os.remove(ppt_file)

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user)

    credit = get_user_credit(user.id)

    msg = (
        f"👤 ID: {user.id}\n"
        f"👤 Name: {user.first_name}\n"
        f"🔗 Username: @{user.username}\n"
        f"💰 Credit: {credit}\n\n"
        f"📞 Credit ke liye call kare:\n{CONTACT_NUMBER}\n\n"
        f"👉 PPT ke liye /objective use karo"
    )

    await update.message.reply_text(msg)

# ===== OBJECTIVE =====
async def objective_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["objective_mode"] = True
    await update.message.reply_text("✅ Mode ON — ab bhejo")

# ===== ADMIN =====
async def admin_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Password bhejo")
    context.user_data["admin_pass"] = True

async def add_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admin_sessions:
        return

    try:
        uid = int(context.args[0])
        amt = int(context.args[1])

        current = get_user_credit(uid)
        update_user_credit(uid, current + amt)

        await update.message.reply_text("Credit added")
    except:
        await update.message.reply_text("Usage: /addcredit user_id amount")

# ===== TEXT =====
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user)

    # admin login
    if context.user_data.get("admin_pass"):
        if update.message.text == ADMIN_PASSWORD:
            admin_sessions.add(user.id)
            await update.message.reply_text("Admin login success")
        else:
            await update.message.reply_text("Wrong password")
        context.user_data["admin_pass"] = False
        return

    # objective check
    if not context.user_data.get("objective_mode"):
        await update.message.reply_text("❌ Pehle /objective use karo")
        return

    fixed = generate_ai(FIX_PROMPT + update.message.text)
    questions = [q.strip() for q in re.split(r"\n(?=प्रश्न)", fixed) if q.strip()]

    if not questions:
        await update.message.reply_text("❌ No question")
        return

    slides = len(questions)
    cost = slides * 25

    credit = get_user_credit(user.id)

    if credit < cost:
        await update.message.reply_text(
            f"❌ Credit kam\nSlides: {slides}\nNeed: {cost}\nHave: {credit}"
        )
        return

    new_credit = credit - cost
    update_user_credit(user.id, new_credit)

    await make_ppt(update, questions)

    await update.message.reply_text(
        f"✅ PPT Ready\nSlides: {slides}\nUsed: {cost}\nLeft: {new_credit}"
    )

    context.user_data["objective_mode"] = False

# ===== IMAGE =====
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user)

    if not context.user_data.get("objective_mode"):
        await update.message.reply_text("❌ Pehle /objective use karo")
        return

    await update.message.reply_text("📸 Processing...")

    photo = update.message.photo[-1]
    file = await photo.get_file()

    path = "img.jpg"
    await file.download_to_drive(path)

    img = Image.open(path)
    text = pytesseract.image_to_string(img)

    os.remove(path)

    fixed = generate_ai(FIX_PROMPT + text)
    questions = [q.strip() for q in re.split(r"\n(?=प्रश्न)", fixed) if q.strip()]

    if not questions:
        await update.message.reply_text("❌ No question")
        return

    slides = len(questions)
    cost = slides * 25

    credit = get_user_credit(user.id)

    if credit < cost:
        await update.message.reply_text(
            f"❌ Credit kam\nSlides: {slides}\nNeed: {cost}\nHave: {credit}"
        )
        return

    new_credit = credit - cost
    update_user_credit(user.id, new_credit)

    await make_ppt(update, questions)

    await update.message.reply_text(
        f"✅ PPT Ready\nSlides: {slides}\nUsed: {cost}\nLeft: {new_credit}"
    )

    context.user_data["objective_mode"] = False

# ===== PDF =====
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user)

    if not context.user_data.get("objective_mode"):
        await update.message.reply_text("❌ Pehle /objective use karo")
        return

    await update.message.reply_text("📄 Processing PDF...")

    doc = update.message.document
    file = await doc.get_file()

    path = "file.pdf"
    await file.download_to_drive(path)

    text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t

    os.remove(path)

    fixed = generate_ai(FIX_PROMPT + text)
    questions = [q.strip() for q in re.split(r"\n(?=प्रश्न)", fixed) if q.strip()]

    if not questions:
        await update.message.reply_text("❌ No question")
        return

    slides = len(questions)
    cost = slides * 25

    credit = get_user_credit(user.id)

    if credit < cost:
        await update.message.reply_text(
            f"❌ Credit kam\nSlides: {slides}\nNeed: {cost}\nHave: {credit}"
        )
        return

    new_credit = credit - cost
    update_user_credit(user.id, new_credit)

    await make_ppt(update, questions)

    await update.message.reply_text(
        f"✅ PPT Ready\nSlides: {slides}\nUsed: {cost}\nLeft: {new_credit}"
    )

    context.user_data["objective_mode"] = False

# ===== MAIN =====
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("objective", objective_mode))
    app.add_handler(CommandHandler("admin", admin_login))
    app.add_handler(CommandHandler("addcredit", add_credit))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))

    print("🚀 Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
