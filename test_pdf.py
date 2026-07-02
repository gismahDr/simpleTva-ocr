from app.pdf_service import pdf_to_images
from app.ocr_service import extract_text_from_images, extract_operations


images = pdf_to_images("releve.pdf")


result = extract_text_from_images(images)


operations = extract_operations(result)


for op in operations:
    print(op)