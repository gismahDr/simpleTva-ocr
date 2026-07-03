from pdf2image import convert_from_path
import os
import shutil

POPPLER_PATH = os.environ.get("POPPLER_PATH")


def _detect_type(path):
    with open(path, "rb") as f:
        header = f.read(8)
    if header[:5] == b"%PDF-":
        return "pdf"
    if header[:4] == b"\x89PNG":
        return "png"
    if header[:2] in (b"\xff\xd8",):
        return "jpg"
    if header[:4] == b"RIFF":
        f.seek(8)
        if f.read(4) == b"WEBP":
            return "webp"
        return None
    return None


def file_to_images(file_path):

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    file_type = _detect_type(file_path)
    if file_type is None:
        raise ValueError(f"Unsupported file type")

    output_dir = "temp_images"
    os.makedirs(output_dir, exist_ok=True)

    if file_type == "pdf":
        kwargs = {"dpi": 300}
        if POPPLER_PATH:
            kwargs["poppler_path"] = POPPLER_PATH
        pages = convert_from_path(file_path, **kwargs)
        images = []
        for index, page in enumerate(pages):
            image_path = f"{output_dir}/page_{index + 1}.png"
            page.save(image_path, "PNG")
            images.append(image_path)
        return images
    else:
        ext = "png" if file_type == "png" else "jpg"
        dest = f"{output_dir}/page_1.{ext}"
        shutil.copy2(file_path, dest)
        return [dest]