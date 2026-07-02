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


HEADER_FOOTER_PATTERNS = re.compile(
    r"RELEVE DE COMPTE|LIBELLE|VALEUR|DEBIT|CREDIT|REPORT\b|Total Mouvements|"
    r"Solde au|Agence|Compte|R\.I\.B\.|NOUS AVONS|EN CAS DE|"
    r"Devise\s*:|Dirham|EL JADIDA|RUE LIEUTENANT|BP \d+|CASA|"
    r"saurions|GEMENT|UN ENGAGEMENT",
    re.IGNORECASE
)


def _is_header_or_footer(text):
    return bool(HEADER_FOOTER_PATTERNS.search(text)) if text else False


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
    current_page = -1

    for page_idx, page in enumerate(results):
        if not page:
            continue

        page_width = max(item["box"][2][0] for item in page)
        rows = _group_by_rows(page, y_tolerance=20)

        for row in rows:

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

            libelle_text = " ".join(libelle_parts) if libelle_parts else ""

            if date_operation_val:
                if current and current["libelle"].strip():
                    operations.append(current)
                current = {
                    "date_operation": date_operation_val,
                    "date_valeur": date_valeur_val,
                    "libelle": libelle_text,
                    "debit": debit_val,
                    "credit": credit_val
                }
                current_page = page_idx
            elif current:
                if _is_header_or_footer(libelle_text):
                    continue

                if libelle_text:
                    if current["libelle"]:
                        current["libelle"] += " " + libelle_text
                    else:
                        current["libelle"] = libelle_text

                if debit_val and not current["debit"] and not current["credit"]:
                    current["debit"] = debit_val
                if credit_val and not current["credit"] and not current["debit"]:
                    current["credit"] = credit_val
                if date_valeur_val and not current["date_valeur"]:
                    current["date_valeur"] = date_valeur_val

    if current and current["libelle"].strip():
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