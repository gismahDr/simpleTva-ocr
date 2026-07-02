from paddleocr import PaddleOCR
import re


ocr = PaddleOCR(
    lang="fr",
    use_angle_cls=True
)

DATE_FULL = re.compile(r"^\d{1,2}/\d{2}/\d{4}$")
DATE_SHORT = re.compile(r"^\d{1,2}/\d{2}$")
AMOUNT_PATTERN = re.compile(r"^\d+(?: \d{3})*,\d{2}$")

COLUMN_RANGES = [
    ("date_operation", 0.00, 0.12),
    ("libelle",        0.12, 0.72),
    ("date_valeur",    0.72, 0.82),
    ("debit",          0.82, 0.92),
    ("credit",         0.92, 1.01),
]


BANK_PROFILES = {
    "cih": {
        "y_tolerance": 10,
        "footer_keywords": [
            r"NOUVEAU SOLDE", r"TOTAL DES MOUVEMENTS", r"PAGE[N]?\s",
            r"SAUF ERREUR", r"RELEVE D'IDENTITE", r"VOTRE CONSEILLER",
        ],
        "debit_keywords": [
            r"RETRAIT", r"PAIEMENT", r"TIMBRE", r"DROIT DE TIMBRE",
            r"RECHARGE", r"CARTE",
        ],
        "credit_keywords": [
            r"REMISE", r"VIREMENT\s+RECU", r"VIR\s+RECU",
        ],
        "min_debit_end": 0.88,
        "pad_dates": True,
    },
    "generic": {
        "y_tolerance": 10,
        "footer_keywords": [],
        "debit_keywords": [],
        "credit_keywords": [],
        "min_debit_end": 0.85,
        "pad_dates": False,
    },
}


def _detect_bank(lines):
    text_block = " ".join(item["text"] for item in lines).upper()
    has_cih = "CIH" in text_block and "BANK" in text_block
    if has_cih:
        return "cih"
    return "generic"


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
    t = text.strip()
    if DATE_FULL.match(t):
        return t
    if DATE_SHORT.match(t):
        return t
    return None


def _pad_day(d):
    parts = d.split("/")
    if len(parts[0]) == 1:
        parts[0] = "0" + parts[0]
    return "/".join(parts)


def _extract_date(text, pad=False):
    t = text.strip()
    d = _is_date(t)
    if d:
        return _pad_day(d) if pad else d
    m = re.match(r"(\d{1,2}/\d{2})(?:\d{1,2}/\d{2,4})", t)
    if m:
        return _pad_day(m.group(1))
    m = re.match(r"(\d{1,2}/\d{2})\d+/\d{2}", t)
    if m:
        return _pad_day(m.group(1))
    return None


def _extract_date_with_remainder(text, pad=False):
    t = text.strip()
    d = _is_date(t)
    if d:
        return (_pad_day(d) if pad else d), t[len(d):].strip()
    m = re.match(r"(\d{1,2}/\d{2})(\d{1,2}/\d{2,4})", t)
    if m:
        return _pad_day(m.group(1)), m.group(2)
    m = re.match(r"(\d{1,2}/\d{2})(\d+/\d{2})", t)
    if m:
        return _pad_day(m.group(1)), m.group(2)
    return None, t


def _is_amount(text):
    return bool(AMOUNT_PATTERN.match(text.strip()))


def _classify_column(x_center, page_width, ranges=None):
    if page_width <= 0:
        return "libelle"
    ratio = x_center / page_width
    for name, start, end in (ranges or COLUMN_RANGES):
        if start <= ratio < end:
            return name
    return "libelle"


def _detect_column_ranges(header_row, page_width, min_debit_end=0.85):
    col_x = {}
    for item, x, y in header_row:
        text = item["text"].strip().lower()
        if re.search(r"^date", text):
            col_x.setdefault("date", x)
        if re.search(r"valeur", text):
            col_x.setdefault("valeur", x)
        if re.search(r"libell[ée]|op[eé]ration|r[ée]f[ée]rence", text):
            col_x.setdefault("libelle", x)
        if re.search(r"d[ée]bit", text):
            col_x["debit"] = x
        if re.search(r"cr[ée]dit", text):
            col_x["credit"] = x
        if re.search(r"montant", text):
            col_x.setdefault("montant", x)

    if len(col_x) < 3:
        return COLUMN_RANGES

    sorted_cols = sorted(col_x.items(), key=lambda kv: kv[1])

    col_order = []
    for name, x in sorted_cols:
        if name == "date":
            if not col_order or col_order[-1][0] != "date_operation":
                col_order.append(("date_operation", x))
        elif name == "valeur":
            col_order.append(("date_valeur", x))
        elif name == "montant":
            has_debit = any(n == "debit" for n, _ in col_order)
            col_order.append(("debit" if not has_debit else "credit", x))
        else:
            col_order.append((name, x))

    ranges = []
    prev_ratio = 0.0
    for i, (name, x) in enumerate(col_order):
        r = x / page_width
        if i < len(col_order) - 1:
            next_r = col_order[i + 1][1] / page_width
            end = (r + next_r) / 2
        else:
            end = 1.01
        ranges.append((name, prev_ratio, end))
        prev_ratio = end

    for i, (name, start, end) in enumerate(ranges):
        if name == "debit" and end < min_debit_end:
            ranges[i] = (name, start, end + 0.04)
            prev_ratio = end + 0.04
    for i, (name, start, end) in enumerate(ranges):
        if name == "credit" and start < min_debit_end:
            ranges[i] = (name, min_debit_end, end)

    return ranges


def _group_by_rows(items, y_tolerance=10):

    enriched = []
    for item in items:
        box = item["box"]
        y_center = (box[0][1] + box[2][1]) / 2
        x_center = (box[0][0] + box[2][0]) / 2
        enriched.append((item, x_center, y_center))

    enriched.sort(key=lambda x: (x[2], x[1]))

    rows = []
    current_row = []
    row_anchor_y = None

    for item, x, y in enriched:
        if row_anchor_y is None:
            current_row = [(item, x, y)]
            row_anchor_y = y
        elif abs(y - row_anchor_y) <= y_tolerance:
            current_row.append((item, x, y))
        else:
            current_row.sort(key=lambda x: x[1])
            rows.append(current_row)
            current_row = [(item, x, y)]
            row_anchor_y = y

    if current_row:
        current_row.sort(key=lambda x: x[1])
        rows.append(current_row)

    return rows


def extract_operations(results, bank=None):

    if bank is None:
        all_lines = [item for page in results for item in page]
        bank = _detect_bank(all_lines)

    profile = BANK_PROFILES.get(bank, BANK_PROFILES["generic"])
    pad = profile["pad_dates"]
    y_tolerance = profile["y_tolerance"]
    min_debit_end = profile["min_debit_end"]
    footer_pattern = re.compile(
        "|".join(profile["footer_keywords"]), re.IGNORECASE
    ) if profile["footer_keywords"] else None
    debit_keywords = re.compile(
        "|".join(profile["debit_keywords"]), re.IGNORECASE
    ) if profile["debit_keywords"] else None
    credit_keywords = re.compile(
        "|".join(profile["credit_keywords"]), re.IGNORECASE
    ) if profile["credit_keywords"] else None

    operations = []
    current = None

    for page in results:
        if not page:
            continue

        page_width = max(item["box"][2][0] for item in page)
        rows = _group_by_rows(page, y_tolerance=y_tolerance)

        header_idx = -1
        header_row = None
        for i, row in enumerate(rows):
            text = " ".join(item[0]["text"] for item in row)
            if re.search(r"date", text, re.I) and re.search(
                r"libell[ée]|op[eé]ration|r[ée]f[ée]rence", text, re.I
            ):
                header_idx = i
                header_row = row
                break

        if header_idx < 0:
            continue

        col_ranges = (
            _detect_column_ranges(header_row, page_width, min_debit_end)
            if header_row else COLUMN_RANGES
        )

        for row in rows[header_idx + 1:]:

            row.sort(key=lambda x: x[1])

            row_text = " ".join(item[0]["text"] for item in row)
            if footer_pattern and footer_pattern.search(row_text):
                continue

            date_operation_val = ""
            date_valeur_val = ""
            libelle_parts = []
            debit_val = ""
            credit_val = ""
            pending_text = []

            for item, x_center, y_center in row:
                text = item["text"].strip()
                if not text:
                    continue

                col = _classify_column(x_center, page_width, col_ranges)

                d, remainder = _extract_date_with_remainder(text, pad=pad)
                if d:
                    if not date_operation_val:
                        date_operation_val = d
                    elif not date_valeur_val:
                        date_valeur_val = d
                    else:
                        libelle_parts.append(d)
                    if remainder:
                        pending_text.append((remainder, col))
                elif _is_amount(text):
                    if col == "debit" and not debit_val:
                        debit_val = text
                    elif col == "credit" and not credit_val:
                        credit_val = text
                    else:
                        libelle_parts.append(text)
                else:
                    libelle_parts.append(text)

            for txt, col in pending_text:
                d = _extract_date(txt, pad=pad)
                if d:
                    if not date_valeur_val:
                        date_valeur_val = d
                    else:
                        libelle_parts.append(txt)
                elif _is_amount(txt):
                    if col == "debit" and not debit_val:
                        debit_val = txt
                    elif col == "credit" and not credit_val:
                        credit_val = txt
                    else:
                        libelle_parts.append(txt)
                else:
                    libelle_parts.append(txt)

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
            m = re.match(r"^(\d{2}/\d{2}/\d{4}|\d{2}/\d{2})\s*", op["libelle"])
            if m:
                candidate = m.group(1)
                if candidate != op["date_operation"]:
                    op["date_valeur"] = candidate
                    op["libelle"] = op["libelle"][m.end():].strip()

        if not op["debit"] and not op["credit"]:
            continue
        if op["libelle"].strip().startswith("SOLDEDEPART"):
            continue
        if (len(op["libelle"]) >= 200
                or "RELEVE DE COMPTE" in op["libelle"]
                or not op["libelle"].strip()):
            continue

        if debit_keywords or credit_keywords:
            lib = op["libelle"].upper()
            is_debit_word = bool(debit_keywords and debit_keywords.search(lib))
            is_credit_word = bool(credit_keywords and credit_keywords.search(lib))

            if is_debit_word and not is_credit_word and op["credit"] and not op["debit"]:
                op["debit"] = op["credit"]
                op["credit"] = ""
            elif is_credit_word and not is_debit_word and op["debit"] and not op["credit"]:
                op["credit"] = op["debit"]
                op["debit"] = ""

        cleaned.append(op)

    return cleaned
