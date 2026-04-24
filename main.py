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

# 🔥 Firebase
import firebase_admin
from firebase_admin import credentials, firestore
import json

firebase_json = os.getenv("FIREBASE_CREDENTIALS")
cred = credentials.Certificate(json.loads(firebase_json))
firebase_admin.initialize_app(cred)
db = firestore.client()

# 🔥 ADMIN
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

admin_sessions = set()

# ===== CONFIG =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
CONTACT_NUMBER = os.getenv("CONTACT_NUMBER", "XXXXXXXXXX")

# ===== AI KEYS =====
GEMINI_KEYS = [
    os.getenv("GEMINI_API_KEY"),
    os.getenv("GEMINI_API_KEY1"),
]

GROQ_KEYS = [
    os.getenv("GROQ_API_KEY"),
]

AICREDITS_KEY = os.getenv("AICREDITS_API_KEY")

GEMINI_KEYS = [k for k in GEMINI_KEYS if k]
GROQ_KEYS = [k for k in GROQ_KEYS if k]

gemini_models = []
for key in GEMINI_KEYS:
    genai.configure(api_key=key)
    gemini_models.append(genai.GenerativeModel("gemini-2.5-flash"))

groq_clients = [Groq(api_key=k) for k in GROQ_KEYS]

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
FIX_PROMPT = """तुम एक हिंदी MCQ generator हो...
TEXT:
"""

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
        f"👉 PPT banane ke liye /objective use kare"
    )

    await update.message.reply_text(msg)

# ===== OBJECTIVE =====
async def objective_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["objective_mode"] = True
    await update.message.reply_text("✅ Mode ON — ab data bhejo")

# ===== ADMIN =====
async def admin_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Password bhejo")
    context.user_data["admin_pass"] = True

async def admin_logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_sessions.discard(update.effective_user.id)
    await update.message.reply_text("Logout")

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
        await update.message.reply_text("❌ /objective use karo")
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
        await update.message.reply_text(f"❌ Credit kam\nNeed {cost}, have {credit}")
        return

    update_user_credit(user.id, credit - cost)

    await make_ppt(update, questions)

    context.user_data["objective_mode"] = False

# ===== MAIN =====
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("objective", objective_mode))
    app.add_handler(CommandHandler("admin", admin_login))
    app.add_handler(CommandHandler("logout", admin_logout))
    app.add_handler(CommandHandler("addcredit", add_credit))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🚀 Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
