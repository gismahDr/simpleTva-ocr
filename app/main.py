from fastapi import FastAPI, UploadFile
from app.pdf_service import pdf_to_images
from app.ocr_service import extract_text_from_images, extract_operations
import shutil
import os


app = FastAPI()


@app.get("/")
def home():
    return {
        "status": "OCR Service OK"
    }


@app.post("/ocr")
async def ocr(file: UploadFile):

    path = "temp/input.pdf"

    with open(path, "wb") as buffer:
        buffer.write(await file.read())


    images = pdf_to_images(path)

    ocr_result = extract_text_from_images(images)

    result = extract_operations(ocr_result)


    return {
        "data": result
    }