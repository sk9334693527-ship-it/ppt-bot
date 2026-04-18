from pdf2image import convert_from_path

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📄 Large PDF process ho raha hai... ⏳")

    try:
        doc = update.message.document
        file = await doc.get_file()

        path = "file.pdf"
        await file.download_to_drive(path)

        # convert all pages
        images = convert_from_path(path, dpi=200)

        os.remove(path)

        total_pages = len(images)
        await update.message.reply_text(f"📊 Total pages: {total_pages}")

        prs = Presentation()

        batch_size = 3  # safe limit

        for i in range(0, total_pages, batch_size):
            batch = images[i:i+batch_size]

            await update.message.reply_text(f"⚙️ Processing pages {i+1} to {i+len(batch)}")

            for img in batch:
                prompt = """
Is image me jo MCQ questions hain unhe EXACT same likho.

RULES:
- Question change mat karo
- Language same rakho
- Sirf MCQ format
- No explanation

FORMAT:

Question
A)
B)
C)
D)
"""

                response = model.generate_content([prompt, img])
                data = response.text

                # PPT add
                for block in data.split("\n\n"):
                    lines = [l.strip() for l in block.split("\n") if l.strip()]
                    if len(lines) < 2:
                        continue

                    slide = prs.slides.add_slide(prs.slide_layouts[1])
                    slide.shapes.title.text = lines[0]

                    tf = slide.placeholders[1].text_frame
                    tf.text = ""

                    for l in lines[1:]:
                        tf.add_paragraph().text = l

        file_name = "large_output.pptx"
        prs.save(file_name)

        with open(file_name, "rb") as f:
            await update.message.reply_document(InputFile(f))

        os.remove(file_name)

        await update.message.reply_text("✅ DONE — Large PDF convert ho gaya")

    except Exception as e:
        await update.message.reply_text(f"❌ ERROR:\n{str(e)}")
