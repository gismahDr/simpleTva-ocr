from fastapi import FastAPI, UploadFile
from app.pdf_service import file_to_images
from app.ocr_service import extract_text_from_images, extract_operations
import os


app = FastAPI()


@app.get("/")
def home():
    return {
        "status": "OCR Service OK"
    }


@app.post("/ocr")
async def ocr(file: UploadFile):

    os.makedirs("temp", exist_ok=True)
    ext = os.path.splitext(file.filename)[1] or ".pdf"
    path = f"temp/input{ext}"

    with open(path, "wb") as buffer:
        buffer.write(await file.read())

    images = file_to_images(path)

    ocr_result = extract_text_from_images(images)

    result = extract_operations(ocr_result)

    return {
        "data": result
    }