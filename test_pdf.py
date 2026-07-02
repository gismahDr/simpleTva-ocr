from app.pdf_service import pdf_to_images
from app.ocr_service import extract_text_from_images, extract_operations


images = pdf_to_images("releve.pdf")

result = extract_text_from_images(images)

operations = extract_operations(result)

print(f"Total operations: {len(operations)}")
print("\nOperations containing 26005772:")
for op in operations:
    if "26005772" in op["libelle"]:
        print(f"  {op}")

print("\nLast 4 operations:")
for op in operations[-4:]:
    print(f"  {op}")
