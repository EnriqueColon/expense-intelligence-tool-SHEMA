import fitz
import pandas as pd


def parse_pdf_text(uploaded_file):
    pdf_lines = []
    with fitz.open(stream=uploaded_file.read(), filetype="pdf") as doc:
        for page in doc:
            text = page.get_text()
            lines = text.split("\n")
            pdf_lines.extend(lines)
    return pdf_lines


def extract_transactions_from_text(lines):
    transactions = []
    i = 0

    while i < len(lines) - 2:
        line_1 = lines[i].strip()
        line_2 = lines[i + 1].strip()
        line_3 = lines[i + 2].strip()

        # Payment transaction (3-line pattern)
        if (
            len(line_1) >= 4 and line_1[:2].isdigit() and
            "PAYMENT" in line_2.upper() and
            ("minus$" in line_3 or "-$" in line_3 or line_3.startswith("-"))
        ):
            amount = (
                line_3.replace("minus$", "-")
                      .replace("$", "")
                      .replace(",", "")
                      .strip()
            )
            transactions.append({
                "Sale Date": line_1,
                "Post Date": line_1,
                "Description": line_2,
                "Amount": amount
            })
            i += 3
            continue

        # Purchase transaction (4-line pattern)
        if i < len(lines) - 3:
            line_4 = lines[i + 3].strip()
            if (
                len(line_1) >= 4 and line_1[:2].isdigit() and
                len(line_2) >= 4 and line_2[:2].isdigit() and
                "$" in line_4
            ):
                amount = (
                    line_4.replace("$", "")
                          .replace(",", "")
                          .strip()
                )
                transactions.append({
                    "Sale Date": line_1,
                    "Post Date": line_2,
                    "Description": line_3,
                    "Amount": amount
                })
                i += 4
                continue

        i += 1

    return pd.DataFrame(transactions)
