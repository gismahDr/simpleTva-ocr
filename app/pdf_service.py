from pdf2image import convert_from_path
import os


def pdf_to_images(pdf_path):

    output_dir = "temp_images"

    os.makedirs(output_dir, exist_ok=True)

    pages = convert_from_path(
        pdf_path,
        dpi=300,
        poppler_path=r"E:\Downloads\poppler\Library\bin"
    )

    images = []

    for index, page in enumerate(pages):

        image_path = f"{output_dir}/page_{index + 1}.png"

        page.save(
            image_path,
            "PNG"
        )

        images.append(image_path)

    return images