from paddleocr import PaddleOCR
import re
import threading


_ocr = None
_ocr_lock = threading.Lock()


def _get_ocr():
    global _ocr
    if _ocr is None:
        with _ocr_lock:
            if _ocr is None:
                _ocr = PaddleOCR(lang="fr", use_angle_cls=True)
    return _ocr

DATE_FULL = re.compile(r"^\d{1,2}/\d{2}/\d{4}$")
DATE_SHORT = re.compile(r"^\d{1,2}/\d{2}$")
DATE_FULL_SPACE = re.compile(r"^\d{1,2}\s+\d{2}\s+\d{4}$")
DATE_SHORT_SPACE = re.compile(r"^\d{1,2}\s+\d{2}$")
DATE_SHORT_YEAR = re.compile(r"^\d{1,2}\s+\d{2}\s+\d{2}$")
DATE_COMPRESSED = re.compile(r"^(\d{2})(\d{2})(\d{4})$")
DATE_SPLIT_YEAR = re.compile(r"^(\d{1,2})\s+(\d{2})(\d{4})$")
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
    "attijari": {
        "y_tolerance": 10,
        "footer_keywords": [
            r"TOTAL MOUVEMENTS", r"SOLDE FINAL", r"SOLDE DEPART",
            r"PAGE\s*\d+", r"SAUF ERREUR",
        ],
        "debit_keywords": [
            r"RETRAIT", r"PAIEMENT", r"TIMBRE", r"FRAIS",
            r"PRELEVEMENT", r"CHEQUE", r"VIR\.EMIS",
            r"OPERATION AU DEBIT",
        ],
        "credit_keywords": [
            r"VIREMENT\s+RECU", r"VIR\s+RECU", r"VERSEMENT",
            r"REMISE", r"CREDIT",
        ],
        "min_debit_end": 0.78,
        "pad_dates": False,
    },
    "bp": {
        "y_tolerance": 10,
        "footer_keywords": [
            r"SOLDE A REPORTER", r"ANCIEN SOLDE", r"TOTAL",
        ],
        "debit_keywords": [
            r"RETRAIT", r"COMMISSION", r"TAXE SUR VALEUR AJOUTEE",
            r"CHEQUE", r"TIMBRE",
        ],
        "credit_keywords": [
            r"VIREMENT", r"ENCAISSEMENT", r"VERSEMENT",
            r"REMISE",
        ],
        "min_debit_end": 0.80,
        "pad_dates": False,
    },
    "cddm": {
        "y_tolerance": 10,
        "footer_keywords": [
            r"NOUVEAU SOLDE", r"TOTAL MOUVEMENTS", r"SAUF ERREUR",
            r"FEUILLET", r"ANCIEN SOLDE",
        ],
        "debit_keywords": [
            r"RETRAIT", r"PRELEVEMENT", r"FRAIS", r"DROIT TIMBRE",
            r"DROIT DE TIMBRE",
        ],
        "credit_keywords": [
            r"VERSEMENT", r"VIREMENT",
        ],
        "min_debit_end": 0.80,
        "pad_dates": False,
    },
    "general": {
        "y_tolerance": 15,
        "footer_keywords": [
            r"TOTAL", r"SOLDE", r"SAUF ERREUR", r"PAGE",
            r"NOUVEAU SOLDE",
        ],
        "debit_keywords": [
            r"RETRAIT", r"PAIEMENT", r"PRELEVEMENT", r"FRAIS",
            r"TIMBRE", r"CHEQUE", r"COMMISSION",
        ],
        "credit_keywords": [
            r"VIREMENT", r"VERSEMENT", r"REMISE", r"ENCAISSEMENT",
            r"CREDIT",
        ],
        "min_debit_end": 0.80,
        "pad_dates": False,
    },
}


def _detect_bank(lines):
    text_block = " ".join(item["text"] for item in lines).upper()
    if "CIH" in text_block and "BANK" in text_block:
        return "cih"
    if "ATTIJARI" in text_block and "WAFA" in text_block:
        return "attijari"
    if "BANQUE POPULAIRE" in text_block:
        return "bp"
    if ("EXTRAIT" in text_block and "BANQUE" in text_block
            and "CREDIT DU MAROC" not in text_block):
        return "bp"
    if "CREDIT DU MAROC" in text_block or "CDDM" in text_block:
        return "cddm"
    return "general"


def extract_text_from_images(images):

    all_results = []

    for image in images:

        print("Analyse :", image)

        result = _get_ocr().ocr(image)

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


def extract_raw_text(results):
    all_items = []
    for page in results:
        for item in page:
            box = item["box"]
            y_center = (box[0][1] + box[2][1]) / 2
            x_center = (box[0][0] + box[2][0]) / 2
            text = item["text"].strip()
            if text:
                all_items.append((y_center, x_center, text))

    all_items.sort(key=lambda t: (t[0], t[1]))

    lines = [t[2] for t in all_items]
    return "\n".join(lines)


def _normalize_date(t):
    t = t.strip()
    if DATE_FULL.match(t):
        return t
    if DATE_SHORT.match(t):
        return t
    if DATE_FULL_SPACE.match(t):
        return re.sub(r"\s+", "/", t)
    if DATE_SHORT_SPACE.match(t):
        return re.sub(r"\s+", "/", t)
    if DATE_SHORT_YEAR.match(t):
        return "/".join(t.split()[:2]) + "/20" + t.split()[2]
    m = DATE_COMPRESSED.match(t)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
    m = DATE_SPLIT_YEAR.match(t)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{int(m.group(1)):02d}/{m.group(2)}/{m.group(3)}"
    return None

def _is_date(text):
    return _normalize_date(text)


def _pad_day(d):
    parts = d.split("/")
    if len(parts[0]) == 1:
        parts[0] = "0" + parts[0]
    return "/".join(parts)


def _extract_date(text, pad=False):
    t = text.strip()
    d = _normalize_date(t)
    if d:
        return _pad_day(d) if pad else d
    m = re.match(r"(\d{1,2}/\d{2})(?:\d{1,2}/\d{2,4})", t)
    if m:
        return _pad_day(m.group(1))
    m = re.match(r"(\d{1,2}/\d{2})\d+/\d{2}", t)
    if m:
        return _pad_day(m.group(1))
    m = re.match(r"(\d{1,2}\s+\d{2})(\d{1,2}/\d{2,4}|\d{1,2}\s+\d{2})", t)
    if m:
        nd = _normalize_date(m.group(1))
        return _pad_day(nd) if pad else nd
    m = re.match(r"(\d{1,2}\s+\d{2})\d+\s+\d{2}", t)
    if m:
        nd = _normalize_date(m.group(1))
        return _pad_day(nd) if pad else nd
    return None


def _extract_date_with_remainder(text, pad=False):
    t = text.strip()
    d = _normalize_date(t)
    if d:
        consumed = len(t)
        return (_pad_day(d) if pad else d), t[consumed:].strip()
    m = re.match(r"(\d{1,2}/\d{2})(\d{1,2}/\d{2,4})", t)
    if m:
        return _pad_day(m.group(1)), m.group(2)
    m = re.match(r"(\d{1,2}/\d{2})(\d+/\d{2})", t)
    if m:
        return _pad_day(m.group(1)), m.group(2)
    m = re.match(r"(\d{1,2}\s+\d{2})\s+(\d{1,2}(?:/\d{2})?)", t)
    if m:
        nd = _normalize_date(m.group(1))
        return (_pad_day(nd) if pad else nd), m.group(2)
    m = re.match(r"(\d{1,2}\s+\d{2})(\d+/\d{2})", t)
    if m:
        nd = _normalize_date(m.group(1))
        return (_pad_day(nd) if pad else nd), m.group(2)
    return None, t


def _is_amount(text):
    t = text.strip().replace("_", " ")
    return bool(AMOUNT_PATTERN.match(t))


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
        if re.search(r"^code$|^code\s", text):
            col_x.setdefault("code", x)
        elif re.search(r"^date", text):
            col_x.setdefault("date", x)
        elif re.search(r"valeur", text):
            col_x.setdefault("valeur", x)
        elif re.search(r"libell[ée]|libel|op[eé]ration|r[ée]f[ée]rence|nature", text):
            col_x.setdefault("libelle", x)
        elif re.search(r"capitaux|d[ée]bit", text):
            col_x["debit"] = x
        elif re.search(r"cr[ée]dit", text):
            col_x["credit"] = x
        elif re.search(r"montant", text):
            col_x.setdefault("montant", x)

    if len(col_x) < 3:
        return COLUMN_RANGES

    sorted_cols = sorted(col_x.items(), key=lambda kv: kv[1])

    col_order = []
    for name, x in sorted_cols:
        if name == "code":
            col_order.append(("code", x))
        elif name == "date":
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

    profile = BANK_PROFILES.get(bank, BANK_PROFILES["general"])
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
                r"libell?[ée]|libel|op[eé]ration|r[ée]f[ée]rence|code|nature", text, re.I
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
            reference_val = ""
            pending_text = []
            date_valeur_fragments = []

            for item, x_center, y_center in row:
                text = item["text"].strip()
                if not text:
                    continue

                col = _classify_column(x_center, page_width, col_ranges)

                if col == "code":
                    m = re.match(r"^([A-Z0-9]+)\s+(\d{1,2})$", text)
                    if m and not date_operation_val:
                        if not reference_val:
                            reference_val = m.group(1)
                        date_operation_val = f"{int(m.group(2)):02d}"
                    elif not reference_val:
                        reference_val = text
                    else:
                        reference_val += " " + text
                    continue

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
                    amt = text.replace("_", " ")
                    if col == "debit" and not debit_val:
                        debit_val = amt
                    elif col == "credit" and not credit_val:
                        credit_val = amt
                    else:
                        libelle_parts.append(amt)
                else:
                    if bank == "attijari" and col == "date_operation" and not date_operation_val:
                        m = re.match(r"^([A-Z0-9]+)\s+(\d{1,2})$", text)
                        if m:
                            if not reference_val:
                                reference_val = m.group(1)
                            date_operation_val = f"{int(m.group(2)):02d}"
                            continue
                        m = re.match(r"^(\d{1,2})$", text)
                        if m:
                            date_operation_val = f"{int(m.group(1)):02d}"
                            continue
                    if col == "date_valeur":
                        date_valeur_fragments.append(text)
                    else:
                        libelle_parts.append(text)

            if date_valeur_fragments and not date_valeur_val:
                combined = " ".join(date_valeur_fragments)
                d = _extract_date(combined, pad=pad)
                if d:
                    date_valeur_val = d
                else:
                    libelle_parts.extend(date_valeur_fragments)
            elif date_valeur_fragments:
                libelle_parts.extend(date_valeur_fragments)

            for txt, col in pending_text:
                d = _extract_date(txt, pad=pad)
                if d:
                    if not date_valeur_val:
                        date_valeur_val = d
                    else:
                        libelle_parts.append(txt)
                elif _is_amount(txt):
                    amt = txt.replace("_", " ")
                    if col == "debit" and not debit_val:
                        debit_val = amt
                    elif col == "credit" and not credit_val:
                        credit_val = amt
                    else:
                        libelle_parts.append(amt)
                else:
                    libelle_parts.append(txt)

            if not date_operation_val:
                continue

            if bank == "attijari" and date_valeur_val:
                m = re.match(r"^(\d{1,2})$", date_operation_val)
                if m:
                    vm = re.match(r"^(\d{1,2})/(\d{2})(?:/(\d{4}))?$", date_valeur_val)
                    if vm:
                        month = vm.group(2)
                        year = vm.group(3) if vm.group(3) else ""
                        date_operation_val = f"{int(m.group(1)):02d}/{month}"
                        if year:
                            date_operation_val += f"/{year}"

            if current:
                operations.append(current)
            current = {
                "reference": reference_val,
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


INVOICE_NUMBER_RE = re.compile(
    r"(?:facture|invoice|fact\.?|n[o°]|ref|réf|invoice\s*#)\s*[:\s]*(\S+)",
    re.IGNORECASE,
)
INVOICE_DATE_RE = re.compile(
    r"(?:date\s*(?:de\s*(?:facturation|livraison|émission)?)?|invoice\s*date)\s*[:\s]*",
    re.IGNORECASE,
)
SUPPLIER_KEYWORDS = re.compile(
    r"(?:fournisseur|vendeur|exp[ée]diteur|supplier|vendor|emettrice?\b)",
    re.IGNORECASE,
)
CLIENT_KEYWORDS = re.compile(
    r"(?:facture\s+[àa]|livr[ée]\s+[àa]|client|destinataire|bill\s*to|ship\s*to|adresse\s*(?:de\s*)?livraison|acheteur)",
    re.IGNORECASE,
)
ICE_RE = re.compile(r"ICE\s*[:\s]*(\d{15})", re.IGNORECASE)
RC_RE = re.compile(r"(?:RC|R\.C\.?|Registre\s*Commerce)\s*[:\s]*(\S+)", re.IGNORECASE)
PATENTE_RE = re.compile(r"(?:patente|Pat\.?)\s*[:\s]*(\S+)", re.IGNORECASE)
IF_RE = re.compile(r"(?:IF|I\.F\.?|Identifiant\s*Fiscal)\s*[:\s]*(\S+)", re.IGNORECASE)
CNSS_RE = re.compile(r"(?:CNSS|C\.N\.S\.S\.?)\s*[:\s]*(\S+)", re.IGNORECASE)
IDENTIFIANTS_RE = [ICE_RE, RC_RE, PATENTE_RE, IF_RE, CNSS_RE]
IDENT_NAME_MAP = {
    "ice": "ice", "rc": "rc", "patente": "patente",
    "if_fiscal": "if_fiscal", "cnss": "cnss",
}
IDENT_PAIRS = [
    (ICE_RE, "ice"), (RC_RE, "rc"), (PATENTE_RE, "patente"),
    (IF_RE, "if_fiscal"), (CNSS_RE, "cnss"),
]
AMOUNT_KEYWORDS = re.compile(
    r"(?:ht|hors\s*taxes|base\s*imposable|total\s*ht)",
    re.IGNORECASE,
)
TVATX_KEYWORDS = re.compile(
    r"(?:tva|taxe|vat|t\.v\.a|tvac)",
    re.IGNORECASE,
)
TTC_KEYWORDS = re.compile(
    r"(?:ttc|net\s*[àa]\s*payer|montant\s*du|total\s*ttc|grand\s*total|amount\s*due)",
    re.IGNORECASE,
)
AMOUNT_VAL_RE = re.compile(
    r"(\d+(?:[\s\.]\d{3})*(?:[,.]\d{1,2})?)",
)


def _find_amount_near(items_row, keyword_re):
    for item, x, y in items_row:
        text = item["text"].strip()
        if keyword_re.search(text):
            m = AMOUNT_VAL_RE.search(text)
            if m:
                return m.group(1).strip()
    return ""


def _find_all_ident_positions(all_items):
    found = []
    for item in all_items:
        text = item["text"]
        box = item["box"]
        y_center = (box[0][1] + box[2][1]) / 2
        for pat, name in IDENT_PAIRS:
            m = pat.search(text)
            if m:
                val = m.group(1).strip().strip(":")
                if name == "ice":
                    val = re.sub(r"\s+", "", val)[:15]
                found.append({"name": name, "value": val, "y": y_center, "text": text})
    return found


def _get_name_for_ident(all_items, ident_y, page_width, side=None):
    candidates = []
    for item in all_items:
        box = item["box"]
        y = (box[0][1] + box[2][1]) / 2
        x = (box[0][0] + box[2][0]) / 2
        if abs(y - ident_y) > 30:
            continue
        txt = item["text"].strip()
        if any(pat.search(txt) for pat in IDENTIFIANTS_RE):
            continue
        if INVOICE_NUMBER_RE.search(txt) or INVOICE_DATE_RE.search(txt):
            continue
        if AMOUNT_KEYWORDS.search(txt) or TVATX_KEYWORDS.search(txt) or TTC_KEYWORDS.search(txt):
            continue
        if side == "left" and x >= page_width / 2:
            continue
        if side == "right" and x < page_width / 2:
            continue
        candidates.append((x, txt))
    candidates.sort(key=lambda c: c[0])
    return " ".join(t for _, t in candidates[:3])


def extract_invoice_data(results):
    all_items = [item for page in results for item in page]
    if not all_items:
        return {"error": "Aucun texte détecté"}

    page_width = max(item["box"][2][0] for item in all_items)
    rows = _group_by_rows(all_items, y_tolerance=15)

    invoice = {
        "numero_facture": "",
        "date_facture": "",
        "fournisseur": {"nom": "", "ice": "", "rc": "", "patente": "", "if_fiscal": "", "cnss": ""},
        "client": {"nom": "", "ice": "", "rc": "", "patente": "", "if_fiscal": "", "cnss": ""},
        "designations": [],
        "montant_ht": "",
        "tva": "",
        "total_ttc": "",
    }

    for i, row in enumerate(rows):
        text = " ".join(item[0]["text"] for item in row)

        if INVOICE_NUMBER_RE.search(text) and not invoice["numero_facture"]:
            m = INVOICE_NUMBER_RE.search(text)
            if m:
                invoice["numero_facture"] = m.group(1).strip(": ")

        if INVOICE_DATE_RE.search(text) and not invoice["date_facture"]:
            for item, x, y in row:
                d = _normalize_date(item["text"].strip())
                if d:
                    invoice["date_facture"] = d
                    break

    idents = _find_all_ident_positions(all_items)
    supplier_idents = [i for i in idents if i["y"] < page_width * 0.35]
    client_idents = [i for i in idents if i["y"] >= page_width * 0.35]

    if not supplier_idents and not client_idents and idents:
        mid = page_width * 0.35
        supplier_idents = [i for i in idents if i["y"] < mid]
        client_idents = [i for i in idents if i["y"] >= mid]

    for ident in supplier_idents:
        if not invoice["fournisseur"][ident["name"]]:
            invoice["fournisseur"][ident["name"]] = ident["value"]
            if not invoice["fournisseur"]["nom"]:
                invoice["fournisseur"]["nom"] = _get_name_for_ident(
                    all_items, ident["y"], page_width, side="left"
                )

    for ident in client_idents:
        if not invoice["client"][ident["name"]]:
            invoice["client"][ident["name"]] = ident["value"]
            if not invoice["client"]["nom"]:
                invoice["client"]["nom"] = _get_name_for_ident(
                    all_items, ident["y"], page_width, side="right"
                )

    if not idents:
        for i, row in enumerate(rows[:6]):
            text = " ".join(item[0]["text"] for item in row)
            if CLIENT_KEYWORDS.search(text):
                nom, _, _ = _extract_party_block(rows, i, max_above=0, max_below=4)
                invoice["client"]["nom"] = nom
                break
        for i, row in enumerate(rows[:4]):
            text = " ".join(item[0]["text"] for item in row)
            if not any(pat.search(text) for pat in IDENTIFIANTS_RE):
                if not INVOICE_NUMBER_RE.search(text) and not INVOICE_DATE_RE.search(text):
                    invoice["fournisseur"]["nom"] = " ".join(
                        item[0]["text"] for item in row
                    )[:80]
                    break

    footer_start = len(rows)
    for i, row in enumerate(rows):
        text = " ".join(item[0]["text"] for item in row)
        if TTC_KEYWORDS.search(text):
            footer_start = i
            break

    for i, row in enumerate(rows):
        if i >= footer_start:
            break

        text = " ".join(item[0]["text"] for item in row)

        if TTC_KEYWORDS.search(text) and not invoice["total_ttc"]:
            amt = _find_amount_near(row, TTC_KEYWORDS)
            if amt:
                invoice["total_ttc"] = amt
            continue

        if TVATX_KEYWORDS.search(text) and not invoice["tva"]:
            amt = _find_amount_near(row, TVATX_KEYWORDS)
            if amt:
                invoice["tva"] = amt
            continue

        if AMOUNT_KEYWORDS.search(text) and not invoice["montant_ht"]:
            amt = _find_amount_near(row, AMOUNT_KEYWORDS)
            if amt:
                invoice["montant_ht"] = amt
            continue

        amounts = AMOUNT_VAL_RE.findall(text)
        if amounts and len(row) >= 2:
            desc_parts = []
            for item, x, y in row:
                t = item["text"].strip()
                if not AMOUNT_VAL_RE.match(t):
                    desc_parts.append(t)
            if desc_parts:
                invoice["designations"].append({
                    "description": " ".join(desc_parts),
                    "montants": amounts,
                })

    return invoice


def _extract_party_block(rows, anchor_idx, max_above=4, max_below=2):
    start = max(0, anchor_idx - max_above)
    end = min(len(rows), anchor_idx + max_below + 1)
    block_lines = []
    for i in range(start, end):
        line = " ".join(item[0]["text"] for item in rows[i])
        block_lines.append(line)
    full_text = " | ".join(block_lines)
    idents = _extract_idents_from_text(full_text)
    name_lines = []
    for line in block_lines:
        cleaned = line.strip()
        if not cleaned:
            continue
        if any(pat.search(cleaned) for pat in IDENTIFIANTS_RE):
            continue
        if SUPPLIER_KEYWORDS.search(cleaned) or CLIENT_KEYWORDS.search(cleaned):
            continue
        if INVOICE_NUMBER_RE.search(cleaned) or INVOICE_DATE_RE.search(cleaned):
            continue
        if AMOUNT_KEYWORDS.search(cleaned) or TVATX_KEYWORDS.search(cleaned) or TTC_KEYWORDS.search(cleaned):
            continue
        name_lines.append(cleaned)
    nom = " | ".join(name_lines[:3]) if name_lines else ""
    return nom, idents


def _extract_idents_from_text(text):
    found = {}
    for pat, name in IDENT_PAIRS:
        m = pat.search(text)
        if m:
            val = m.group(1).strip().strip(":")
            if name == "ice":
                val = re.sub(r"\s+", "", val)[:15]
            found[name] = val
    return found
