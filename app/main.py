from fastapi import FastAPI, UploadFile, HTTPException
from app.pdf_service import file_to_images
from app.ocr_service import extract_text_from_images, extract_operations, extract_invoice_data, extract_raw_text
import os
import shutil


app = FastAPI()


@app.get("/")
def home():
    return {
        "status": "OCR Service OK"
    }


MAX_UPLOAD_MB = 20


async def _save_upload(file: UploadFile) -> str:
    content = await file.read()
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_MB}MB)")
    os.makedirs("temp", exist_ok=True)
    ext = os.path.splitext(file.filename)[1] or ".pdf"
    path = f"temp/input{ext}"
    with open(path, "wb") as buffer:
        buffer.write(content)
    return path


def _cleanup():
    for d in ("temp", "temp_images"):
        if os.path.exists(d):
            shutil.rmtree(d)


@app.post("/ocr")
async def ocr(file: UploadFile):
    path = await _save_upload(file)
    try:
        images = file_to_images(path)
        ocr_result = extract_text_from_images(images)
        result = extract_operations(ocr_result)
        return {"data": result}
    finally:
        _cleanup()


@app.post("/ocr/facture")
async def ocr_facture(file: UploadFile):
    path = await _save_upload(file)
    try:
        images = file_to_images(path)
        ocr_result = extract_text_from_images(images)
        result = extract_invoice_data(ocr_result)
        return {"data": result}
    finally:
        _cleanup()


@app.post("/ocr/facture/text")
async def ocr_facture_text(file: UploadFile):
    path = await _save_upload(file)
    try:
        images = file_to_images(path)
        ocr_result = extract_text_from_images(images)
        text = extract_raw_text(ocr_result)
        return {"text": text}
    finally:
        _cleanup()


@app.post("/ocr/facture/ai")
async def ocr_facture_ai(file: UploadFile):
    from app.ai_service import extract_invoice_with_ai_delayed
    path = await _save_upload(file)
    try:
        images = file_to_images(path)
        ocr_result = extract_text_from_images(images)
        text = extract_raw_text(ocr_result)
        result = extract_invoice_with_ai_delayed(text)
        return {"data": result}
    finally:
        _cleanup()
