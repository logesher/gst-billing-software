from flask import current_app
import html as html_module
import os
import re
import textwrap
import unicodedata


PAGE_WIDTH = 595.28
PAGE_HEIGHT = 841.89
LEFT_MARGIN = 40
TOP_MARGIN = 42
BOTTOM_MARGIN = 42
FONT_SIZE = 10
LINE_HEIGHT = 12
WRAP_WIDTH = 92
REPORT_LEFT = 36
REPORT_RIGHT = 36
REPORT_TOP = 56
REPORT_BOTTOM = 42
REPORT_COLS = [
    ("sl_no", 26),
    ("invoice_no", 70),
    ("date", 55),
    ("customer", 145),
    ("amount_without_gst", 90),
    ("tax", 70),
    ("total", 67),
]


def generate_pdf(template_path, context, filename=None):
    """Generate PDF bytes from a Jinja template using WeasyPrint or a local fallback."""
    rendered_html = current_app.jinja_env.get_template(template_path).render(**context)

    try:
        from weasyprint import HTML, CSS

        css_path = os.path.join(current_app.static_folder, 'css', 'invoice.css')
        html = HTML(string=rendered_html, base_url=current_app.root_path)
        return html.write_pdf(stylesheets=[CSS(css_path)] if os.path.exists(css_path) else None)
    except Exception:
        if template_path == 'report_pdf.html':
            return _build_report_table_pdf(context)
        if template_path == 'invoice_pdf.html':
            lines = _invoice_pdf_lines(context)
        else:
            lines = _html_to_lines(rendered_html)
        return _build_text_pdf(lines)


def sanitize_windows_name(value, default="document"):
    cleaned = re.sub(r'[\\/:*?"<>|]+', "-", (value or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or default


def _safe_text(value):
    if value is None:
        return ""
    text = str(value).replace("₹", "Rs. ")
    text = text.replace("\xa0", " ")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _format_money(value):
    return f"Rs. {value or 0:.2f}"


def _invoice_pdf_lines(context):
    invoice = context["invoice"]
    seller = context["seller"]
    customer = invoice.customer
    payments = context.get("payments", [])
    lines = [
        "GST Billing Pro - Tax Invoice",
        f"Invoice No: {invoice.invoice_number}",
        f"Date: {invoice.date.strftime('%d-%b-%Y') if invoice.date else '-'}",
        f"Customer: {customer.name if customer else '-'}",
        f"Owner: {seller.get('name') or '-'}",
        f"PO No: {invoice.po_number or '-'}",
        "Reference No & Date: "
        f"{invoice.reference_number or '-'}"
        f"{' / ' + invoice.reference_date.strftime('%d-%b-%Y') if invoice.reference_date else ''}",
        f"Other References: {invoice.other_references or '-'}",
        "",
        "Items",
    ]

    for index, item in enumerate(invoice.items, start=1):
        lines.append(
            f"{index:02d}. {item.description or '-'} | "
            f"HSN {item.hsn_code or '-'} | "
            f"Qty {item.quantity or 0:.2f} | "
            f"Rate {_format_money(item.rate).replace('Rs. ', '')} | "
            f"Amt {_format_money(item.item_subtotal or 0).replace('Rs. ', '')}"
        )

    lines.extend(
        [
            "",
            f"Subtotal: {_format_money(invoice.subtotal_amount or 0)}",
            f"CGST: {_format_money(invoice.cgst_amount or 0)}",
            f"SGST: {_format_money(invoice.sgst_amount or 0)}",
            f"IGST: {_format_money(invoice.igst_amount or 0)}",
            f"Tax Total: {_format_money(invoice.total_tax or 0)}",
            f"Grand Total: {_format_money(invoice.grand_total or 0)}",
            f"Amount in words: {context.get('amount_in_words') or '-'}",
        ]
    )

    if payments:
        lines.append("")
        lines.append("Payments")
        for payment in payments:
            lines.append(
                f"{payment.payment_date.strftime('%d-%b-%Y') if payment.payment_date else '-'} | "
                f"{_format_money(payment.amount)} | {payment.method or 'Cash'}"
            )
        lines.append(f"Balance: {_format_money(context.get('balance', 0))}")

    return lines


def _report_pdf_lines(context):
    summary = context.get("summary") or {}
    owner = context.get("selected_owner")
    owner_name = owner.name if owner else context.get("owner_label", "All Owners")
    lines = [
        "Monthly Sales Report",
        _safe_text(f"Period: {context.get('period_label') or '-'}"),
        _safe_text(f"Owner: {owner_name}"),
        _safe_text(
            f"Range: {context.get('start_date').strftime('%d-%b-%Y')} to {context.get('end_date').strftime('%d-%b-%Y')}"
            if context.get("start_date") and context.get("end_date")
            else "Range: -"
        ),
        _safe_text(
            "Invoices: {invoice_count} | Amount Without GST: {subtotal} | Tax: {tax} | Grand Total: {grand} | Paid: {paid}".format(
                invoice_count=summary.get("invoice_count", 0),
                subtotal=_format_money(summary.get("subtotal_total", 0)),
                tax=_format_money(summary.get("tax_total", 0)),
                grand=_format_money(summary.get("grand_total", 0)),
                paid=_format_money(summary.get("paid_total", 0)),
            )
        ),
        "",
        "Sl No | Invoice No | Date | Customer | Amount Without GST | Tax | Total",
    ]

    for index, row in enumerate(context.get("report_rows") or [], start=1):
        invoice = row["invoice"]
        lines.append(
            f"{index:02d} | {invoice.invoice_number} | "
            f"{invoice.date.strftime('%d-%b-%Y') if invoice.date else '-'} | "
            f"{invoice.customer.name if invoice.customer else '-'} | "
            f"{_format_money(invoice.subtotal_amount or 0)} | "
            f"{_safe_text(row.get('tax_display') or _format_money(invoice.total_tax or 0))} | "
            f"{_format_money(invoice.grand_total or 0)}"
        )

    if not context.get("report_rows"):
        lines.append("No invoices found for this month.")

    lines.extend(
        [
            "",
            _safe_text(f"Total invoices: {summary.get('invoice_count', 0)}"),
            _safe_text(f"Total amount without GST: {_format_money(summary.get('subtotal_total', 0))}"),
        ]
    )
    return lines


def _build_report_table_pdf(context):
    summary = context.get("summary") or {}
    report_rows = [
        {**row, "index": index}
        for index, row in enumerate(context.get("report_rows") or [], start=1)
    ]
    owner = context.get("selected_owner")
    owner_name = owner.name if owner else context.get("owner_label", "All Owners")
    period_label = context.get("period_label") or "-"
    start_date = context.get("start_date")
    end_date = context.get("end_date")

    pages = _paginate_report_rows(report_rows, top_offset_first=180, top_offset_other=90, row_gap=0)
    page_streams = []

    if not pages:
        pages = [[]]

    for page_index, page_rows in enumerate(pages):
        page_streams.append(
            _report_page_stream(
                page_rows=page_rows,
                page_index=page_index,
                total_pages=len(pages),
                period_label=period_label,
                owner_name=owner_name,
                start_date=start_date,
                end_date=end_date,
                summary=summary,
            )
        )

    return _build_pdf_document(page_streams, include_bold_font=True)


def _paginate_report_rows(rows, top_offset_first, top_offset_other, row_gap=0):
    pages = []
    current_page = []
    remaining_height = PAGE_HEIGHT - REPORT_BOTTOM - top_offset_first
    footer_reserve = 22
    if not rows:
        return [[]]

    for row in rows:
        row_height = _estimate_report_row_height(row)
        if current_page and remaining_height < row_height + row_gap + footer_reserve:
            pages.append(current_page)
            current_page = []
            remaining_height = PAGE_HEIGHT - REPORT_BOTTOM - top_offset_other
        current_page.append(row)
        remaining_height -= row_height + row_gap

    if current_page:
        pages.append(current_page)
    return pages


def _estimate_report_row_height(row):
    cell_values = _report_row_values(row)
    widths = [width for _, width in REPORT_COLS]
    max_lines = 1
    for value, width in zip(cell_values, widths):
        max_lines = max(max_lines, len(_wrap_cell_text(value, width)))
    return max(22, 8 + (max_lines * 12))


def _report_row_values(row):
    invoice = row["invoice"]
    return [
        str(row.get("index", "")),
        invoice.invoice_number or "-",
        invoice.date.strftime("%d-%b-%Y") if invoice.date else "-",
        invoice.customer.name if invoice.customer else "-",
        _format_money(invoice.subtotal_amount or 0),
        row.get("tax_display") or _format_money(invoice.total_tax or 0),
        _format_money(invoice.grand_total or 0),
    ]


def _wrap_cell_text(value, width):
    max_chars = max(8, int(width / 5.2))
    wrapped = textwrap.wrap(
        _safe_text(value),
        width=max_chars,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return wrapped or [""]


def _report_page_stream(page_rows, page_index, total_pages, period_label, owner_name, start_date, end_date, summary):
    commands = []
    row_widths = [width for _, width in REPORT_COLS]
    table_top = PAGE_HEIGHT - REPORT_TOP - (52 if page_index == 0 else 26)
    y = table_top

    if start_date and end_date:
        range_text = f"Owner: {owner_name} | Range: {start_date.strftime('%d-%b-%Y')} to {end_date.strftime('%d-%b-%Y')}"
    else:
        range_text = f"Owner: {owner_name} | Range: -"

    commands.extend(
        [
            "0 0 0 rg",
            "0 0 0 RG",
            "BT",
            "/F2 18 Tf",
            f"1 0 0 1 {REPORT_LEFT} {PAGE_HEIGHT - 28} Tm",
            f"({_pdf_escape('Monthly Sales Report')}) Tj",
            "ET",
            "BT",
            "/F1 10 Tf",
            f"1 0 0 1 {REPORT_LEFT} {PAGE_HEIGHT - 46} Tm",
            f"({_pdf_escape(f'Period: {period_label} - {owner_name}')}) Tj",
            "ET",
            "BT",
            "/F1 9 Tf",
            f"1 0 0 1 {REPORT_LEFT} {PAGE_HEIGHT - 60} Tm",
            f"({_pdf_escape(range_text)}) Tj",
            "ET",
            "BT",
            "/F1 9 Tf",
            f"1 0 0 1 {REPORT_LEFT} {PAGE_HEIGHT - 72} Tm",
            f"({_pdf_escape('Amount values are shown without GST.')}) Tj",
            "ET",
        ]
    )

    summary_line_one = (
        f"Invoices: {summary.get('invoice_count', 0)} | "
        f"Amount Without GST: {_format_money(summary.get('subtotal_total', 0))} | "
        f"Tax: {_format_money(summary.get('tax_total', 0))}"
    )
    summary_line_two = (
        f"Grand Total: {_format_money(summary.get('grand_total', 0))} | "
        f"Paid: {_format_money(summary.get('paid_total', 0))}"
    )
    commands.extend(
        [
            "BT",
            "/F1 8.2 Tf",
            f"1 0 0 1 {REPORT_LEFT} {PAGE_HEIGHT - 84} Tm",
            f"({_pdf_escape(summary_line_one)}) Tj",
            "T*",
            f"({_pdf_escape(summary_line_two)}) Tj",
            "ET",
        ]
    )

    if page_index > 0:
        y -= 10

    header_height = 20
    commands.extend(_draw_report_table_row(
        y=y,
        heights=header_height,
        values=["Sl No.", "Invoice No.", "Date", "Customer", "Amount Without GST", "Tax", "Total"],
        widths=row_widths,
        bold=True,
        fill_gray=0.9,
        center_align=True,
    ))
    y -= header_height

    if not page_rows:
        commands.extend(_draw_report_empty_row(y=y, widths=row_widths, text="No invoices found for this month."))
        return "\n".join(commands)

    for row in page_rows:
        values = _report_row_values(row)
        row_height = _estimate_report_row_height(row)
        commands.extend(_draw_report_table_row(
            y=y,
            heights=row_height,
            values=values,
            widths=row_widths,
            bold=False,
            fill_gray=None,
            center_align=False,
        ))
        y -= row_height

    commands.extend(_draw_report_total_row(y=y, widths=row_widths, summary=summary))
    return "\n".join(commands)


def _draw_report_table_row(y, heights, values, widths, bold=False, fill_gray=None, center_align=False):
    commands = []
    x = REPORT_LEFT
    font_name = "/F2" if bold else "/F1"
    for value, width in zip(values, widths):
        if fill_gray is not None:
            commands.append(f"{fill_gray} g")
            commands.append(f"{x} {y - heights} {width} {heights} re f")
            commands.append("0 g")
        commands.append(f"{x} {y - heights} {width} {heights} re S")
        lines = _wrap_cell_text(value, width - 6)
        text_x = x + 3
        text_y = y - 12
        commands.append("BT")
        commands.append(f"{font_name} 8.5 Tf")
        commands.append("10 TL")
        commands.append(f"1 0 0 1 {text_x} {text_y} Tm")
        for line_index, line in enumerate(lines[:4]):
            rendered_line = _pdf_escape(line)
            if line_index:
                commands.append("T*")
            commands.append(f"({rendered_line}) Tj")
        commands.append("ET")
        x += width
    return commands


def _draw_report_empty_row(y, widths, text):
    total_width = sum(widths)
    height = 24
    commands = [
        f"{REPORT_LEFT} {y - height} {total_width} {height} re S",
        "BT",
        "/F1 8.5 Tf",
        f"1 0 0 1 {REPORT_LEFT + 6} {y - 14} Tm",
        f"({_pdf_escape(text)}) Tj",
        "ET",
    ]
    return commands


def _draw_report_total_row(y, widths, summary):
    commands = []
    x = REPORT_LEFT
    total_cells = [
        ("Total", sum(widths[:4])),
        (_format_money(summary.get("subtotal_total", 0)), widths[4]),
        (_format_money(summary.get("tax_total", 0)), widths[5]),
        (_format_money(summary.get("grand_total", 0)), widths[6]),
    ]
    row_height = 22
    for index, (value, width) in enumerate(total_cells):
        commands.append(f"{x} {y - row_height} {width} {row_height} re S")
        commands.append("BT")
        commands.append("/F2 8.5 Tf" if index == 0 else "/F1 8.5 Tf")
        commands.append("10 TL")
        commands.append(f"1 0 0 1 {x + 3} {y - 12} Tm")
        commands.append(f"({_pdf_escape(value)}) Tj")
        commands.append("ET")
        x += width
    return commands


def _build_pdf_document(page_streams, include_bold_font=False):
    total_objects = 3 + len(page_streams) * 2 + (1 if include_bold_font else 0)
    font_regular_object = 3
    font_bold_object = 4 if include_bold_font else None
    first_page_object = 4 if not include_bold_font else 5
    page_object_numbers = [first_page_object + index * 2 for index in range(len(page_streams))]
    content_object_numbers = [obj + 1 for obj in page_object_numbers]
    output = bytearray()
    offsets = [0] * (total_objects + 1)

    def write(data):
        if isinstance(data, str):
            data = data.encode("latin-1")
        output.extend(data)

    write("%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    offsets[1] = len(output)
    write("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

    offsets[2] = len(output)
    kids = " ".join(f"{page_number} 0 R" for page_number in page_object_numbers)
    write(f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {len(page_streams)} >>\nendobj\n")

    offsets[3] = len(output)
    write("3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

    if include_bold_font:
        offsets[4] = len(output)
        write("4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>\nendobj\n")

    for index, stream in enumerate(page_streams):
        page_number = page_object_numbers[index]
        content_number = content_object_numbers[index]
        stream_bytes = stream.encode("latin-1")
        offsets[page_number] = len(output)
        if include_bold_font:
            resource_font = "<< /F1 3 0 R /F2 4 0 R >>"
        else:
            resource_font = "<< /F1 3 0 R >>"
        write(
            f"{page_number} 0 obj\n"
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font {resource_font} >> /Contents {content_number} 0 R >>\n"
            f"endobj\n"
        )
        offsets[content_number] = len(output)
        write(f"{content_number} 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n")
        write(stream_bytes)
        write("\nendstream\nendobj\n")

    xref_start = len(output)
    write(f"xref\n0 {total_objects + 1}\n")
    write("0000000000 65535 f \n")
    for object_number in range(1, total_objects + 1):
        write(f"{offsets[object_number]:010d} 00000 n \n")
    write(
        f"trailer\n<< /Size {total_objects + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_start}\n%%EOF"
    )
    return bytes(output)


def _html_to_lines(rendered_html):
    text = rendered_html
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(p|div|tr|li|h[1-6]|section|table|thead|tbody|tfoot|ul|ol)>", "\n", text)
    text = re.sub(r"(?is)<(th|td)[^>]*>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", "", text)
    text = html_module.unescape(text)
    lines = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if line:
            lines.append(_safe_text(line))
    return lines


def _wrap_lines(lines):
    wrapped = []
    for line in lines:
        clean_line = _safe_text(line)
        if not clean_line:
            wrapped.append("")
            continue
        wrapped.extend(
            textwrap.wrap(
                clean_line,
                width=WRAP_WIDTH,
                break_long_words=False,
                break_on_hyphens=False,
            )
            or [""]
        )
    return wrapped


def _pdf_escape(text):
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _page_stream(page_lines):
    commands = [
        "BT",
        f"/F1 {FONT_SIZE} Tf",
        f"{LINE_HEIGHT} TL",
        f"1 0 0 1 {LEFT_MARGIN} {PAGE_HEIGHT - TOP_MARGIN} Tm",
    ]
    for index, line in enumerate(page_lines):
        if index:
            commands.append("T*")
        commands.append(f"({_pdf_escape(line)}) Tj")
    commands.append("ET")
    return "\n".join(commands)


def _build_text_pdf(lines):
    wrapped_lines = _wrap_lines(lines)
    max_lines_per_page = int((PAGE_HEIGHT - TOP_MARGIN - BOTTOM_MARGIN) / LINE_HEIGHT)
    pages = [
        wrapped_lines[index:index + max_lines_per_page]
        for index in range(0, len(wrapped_lines), max_lines_per_page)
    ] or [[]]

    page_object_numbers = [4 + index * 2 for index in range(len(pages))]
    content_object_numbers = [5 + index * 2 for index in range(len(pages))]
    total_objects = 3 + len(pages) * 2

    output = bytearray()
    offsets = [0] * (total_objects + 1)

    def write(data):
        if isinstance(data, str):
            data = data.encode("latin-1")
        output.extend(data)

    write("%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    offsets[1] = len(output)
    write("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

    offsets[2] = len(output)
    kids = " ".join(f"{page_number} 0 R" for page_number in page_object_numbers)
    write(f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>\nendobj\n")

    offsets[3] = len(output)
    write("3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>\nendobj\n")

    for index, page_lines in enumerate(pages):
        page_number = page_object_numbers[index]
        content_number = content_object_numbers[index]
        stream = _page_stream(page_lines)
        stream_bytes = stream.encode("latin-1")

        offsets[page_number] = len(output)
        write(
            f"{page_number} 0 obj\n"
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_number} 0 R >>\n"
            f"endobj\n"
        )

        offsets[content_number] = len(output)
        write(f"{content_number} 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n")
        write(stream_bytes)
        write("\nendstream\nendobj\n")

    xref_start = len(output)
    write(f"xref\n0 {total_objects + 1}\n")
    write("0000000000 65535 f \n")
    for object_number in range(1, total_objects + 1):
        write(f"{offsets[object_number]:010d} 00000 n \n")
    write(
        f"trailer\n<< /Size {total_objects + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_start}\n%%EOF"
    )
    return bytes(output)
