from paddleocr import PaddleOCR
import re


ocr = PaddleOCR(
    lang="fr",
    use_angle_cls=True
)

DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")
AMOUNT_PATTERN = re.compile(r"^\d+(?: \d{3})*,\d{2}$")

COLUMN_RANGES = [
    ("date_operation", 0.00, 0.12),
    ("libelle",        0.12, 0.72),
    ("date_valeur",    0.72, 0.82),
    ("debit",          0.82, 0.92),
    ("credit",         0.92, 1.01),
]


def extract_text_from_images(images):

    all_results = []

    for image in images:

        print("Analyse :", image)

        result = ocr.ocr(image)

        lines = []

        for page in result:

            for item in page:

                text = item[1][0]
                confidence = item[1][1]
                box = item[0]

                lines.append({
                    "text": text,
                    "confidence": confidence,
                    "box": box
                })

        all_results.append(lines)

    return all_results


def _is_date(text):
    return bool(DATE_PATTERN.match(text.strip()))


def _is_amount(text):
    return bool(AMOUNT_PATTERN.match(text.strip()))


def _classify_column(x_center, page_width):
    if page_width <= 0:
        return "libelle"
    ratio = x_center / page_width
    for name, start, end in COLUMN_RANGES:
        if start <= ratio < end:
            return name
    return "libelle"


def _group_by_rows(items, y_tolerance=15):

    enriched = []
    for item in items:
        box = item["box"]
        y_center = (box[0][1] + box[2][1]) / 2
        x_center = (box[0][0] + box[2][0]) / 2
        enriched.append((item, x_center, y_center))

    enriched.sort(key=lambda x: (x[2], x[1]))

    rows = []
    current_row = []
    current_y_sum = 0
    current_y_count = 0

    for item, x, y in enriched:
        if not current_row:
            current_row.append((item, x, y))
            current_y_sum = y
            current_y_count = 1
        else:
            avg_y = current_y_sum / current_y_count
            if abs(y - avg_y) <= y_tolerance:
                current_row.append((item, x, y))
                current_y_sum += y
                current_y_count += 1
            else:
                current_row.sort(key=lambda x: x[1])
                rows.append(current_row)
                current_row = [(item, x, y)]
                current_y_sum = y
                current_y_count = 1

    if current_row:
        current_row.sort(key=lambda x: x[1])
        rows.append(current_row)

    return rows


def extract_operations(results):

    operations = []
    current = None

    for page in results:
        if not page:
            continue

        page_width = max(item["box"][2][0] for item in page)
        rows = _group_by_rows(page, y_tolerance=20)

        header_idx = -1
        for i, row in enumerate(rows):
            text = " ".join(item[0]["text"] for item in row).lower()
            if re.search(r"date", text) and re.search(r"libell[ée]", text):
                header_idx = i
                break

        if header_idx < 0:
            continue

        for row in rows[header_idx + 1:]:

            row.sort(key=lambda x: x[1])

            date_operation_val = ""
            date_valeur_val = ""
            libelle_parts = []
            debit_val = ""
            credit_val = ""

            for item, x_center, y_center in row:
                text = item["text"].strip()
                if not text:
                    continue

                col = _classify_column(x_center, page_width)

                if _is_date(text):
                    if not date_operation_val:
                        date_operation_val = text
                    elif not date_valeur_val:
                        date_valeur_val = text
                    else:
                        libelle_parts.append(text)
                elif _is_amount(text):
                    if col == "debit" and not debit_val:
                        debit_val = text
                    elif col == "credit" and not credit_val:
                        credit_val = text
                    else:
                        libelle_parts.append(text)
                else:
                    libelle_parts.append(text)

            if not date_operation_val:
                continue

            if current:
                operations.append(current)
            current = {
                "date_operation": date_operation_val,
                "date_valeur": date_valeur_val,
                "libelle": " ".join(libelle_parts) if libelle_parts else "",
                "debit": debit_val,
                "credit": credit_val
            }

    if current:
        operations.append(current)

    cleaned = []
    for op in operations:
        if not op["date_valeur"] and op["libelle"]:
            m = re.match(r"^(\d{2}/\d{2}/\d{4})\s*", op["libelle"])
            if m:
                candidate = m.group(1)
                if candidate != op["date_operation"]:
                    op["date_valeur"] = candidate
                    op["libelle"] = op["libelle"][m.end():].strip()
        if len(op["libelle"]) < 200 and "RELEVE DE COMPTE" not in op["libelle"]:
            cleaned.append(op)

    return cleaned