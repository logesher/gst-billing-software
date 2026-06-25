from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_file
from flask_login import login_user, logout_user, login_required, current_user
from .models import (User, Customer, Owner, Product, Invoice, InvoiceItem, Payment, db)
from .utils import generate_pdf, sanitize_windows_name
from datetime import date, timedelta
from io import BytesIO
import calendar
from sqlalchemy import func, or_
import os
import re

main = Blueprint('main', __name__)

STATE_CODES = {
    'Andhra Pradesh': '37',
    'Arunachal Pradesh': '12',
    'Assam': '18',
    'Bihar': '10',
    'Chhattisgarh': '22',
    'Goa': '30',
    'Gujarat': '24',
    'Haryana': '06',
    'Himachal Pradesh': '02',
    'Jharkhand': '20',
    'Karnataka': '29',
    'Kerala': '32',
    'Madhya Pradesh': '23',
    'Maharashtra': '27',
    'Manipur': '14',
    'Meghalaya': '17',
    'Mizoram': '15',
    'Nagaland': '13',
    'Odisha': '21',
    'Punjab': '03',
    'Rajasthan': '08',
    'Sikkim': '11',
    'Tamil Nadu': '33',
    'Telangana': '36',
    'Tripura': '16',
    'Uttar Pradesh': '09',
    'Uttarakhand': '05',
    'West Bengal': '19',
    'Delhi': '07',
}

ONES = [
    'Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
    'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen',
    'Seventeen', 'Eighteen', 'Nineteen'
]
TENS = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']


def _state_code(state_name):
    return STATE_CODES.get((state_name or '').strip(), '')


def _number_to_words(number):
    number = int(number)
    if number < 20:
        return ONES[number]
    if number < 100:
        return TENS[number // 10] + (f" {ONES[number % 10]}" if number % 10 else '')
    if number < 1000:
        return ONES[number // 100] + ' Hundred' + (f" {_number_to_words(number % 100)}" if number % 100 else '')
    if number < 100000:
        return _number_to_words(number // 1000) + ' Thousand' + (f" {_number_to_words(number % 1000)}" if number % 1000 else '')
    if number < 10000000:
        return _number_to_words(number // 100000) + ' Lakh' + (f" {_number_to_words(number % 100000)}" if number % 100000 else '')
    return _number_to_words(number // 10000000) + ' Crore' + (f" {_number_to_words(number % 10000000)}" if number % 10000000 else '')


def _amount_to_words(amount):
    rupees = int(amount)
    paise = int(round((amount - rupees) * 100))
    words = f"Indian Rupee {_number_to_words(rupees)}"
    if paise:
        words += f" and {_number_to_words(paise)} Paise"
    return words + ' Only'


def _owner_details(owner=None):
    if owner:
        return {
            'name': owner.name,
            'address': owner.address or '',
            'city': '',
            'gstin': owner.gstin or '',
            'state': owner.state or '',
            'state_code': _state_code(owner.state),
            'phone': owner.phone or '',
            'email': '',
        }
    return {
        'name': current_app.config.get('COMPANY_NAME', ''),
        'address': current_app.config.get('COMPANY_ADDRESS', ''),
        'city': current_app.config.get('COMPANY_CITY', ''),
        'gstin': current_app.config.get('COMPANY_GSTIN', ''),
        'state': current_app.config.get('COMPANY_STATE', ''),
        'state_code': current_app.config.get('COMPANY_STATE_CODE', '') or _state_code(current_app.config.get('COMPANY_STATE', '')),
        'phone': current_app.config.get('COMPANY_PHONE', ''),
        'email': current_app.config.get('COMPANY_EMAIL', ''),
        'irn': current_app.config.get('COMPANY_IRN', ''),
        'ack_no': current_app.config.get('COMPANY_ACK_NO', ''),
        'ack_date': current_app.config.get('COMPANY_ACK_DATE', ''),
    }


def _tax_summary(items):
    rows = {}
    for item in items:
        key = item.hsn_code or 'N/A'
        row = rows.setdefault(
            key,
            {
                'hsn_code': key,
                'taxable_value': 0.0,
                'cgst_rate': item.cgst_rate or 0.0,
                'cgst_amount': 0.0,
                'sgst_rate': item.sgst_rate or 0.0,
                'sgst_amount': 0.0,
                'igst_rate': item.igst_rate or 0.0,
                'igst_amount': 0.0,
                'total_tax_amount': 0.0,
            },
        )
        taxable = item.item_subtotal or 0.0
        cgst_amount = taxable * ((item.cgst_rate or 0.0) / 100)
        sgst_amount = taxable * ((item.sgst_rate or 0.0) / 100)
        igst_amount = taxable * ((item.igst_rate or 0.0) / 100)
        row['taxable_value'] += taxable
        row['cgst_amount'] += cgst_amount
        row['sgst_amount'] += sgst_amount
        row['igst_amount'] += igst_amount
        row['total_tax_amount'] += cgst_amount + sgst_amount + igst_amount

    summary_rows = []
    for row in rows.values():
        for field in ('taxable_value', 'cgst_amount', 'sgst_amount', 'igst_amount', 'total_tax_amount'):
            row[field] = round(row[field], 2)
        summary_rows.append(row)
    return summary_rows


def _invoice_template_context(invoice):
    payments = Payment.query.filter_by(invoice_id=invoice.id).order_by(Payment.payment_date).all()
    total_paid = sum(p.amount for p in payments)
    return {
        'invoice': invoice,
        'payments': payments,
        'total_paid': total_paid,
        'balance': (invoice.grand_total or 0) - total_paid,
        'seller': _owner_details(invoice.owner),
        'customer_state_code': _state_code(invoice.customer.state),
        'amount_in_words': _amount_to_words(invoice.grand_total or 0),
        'tax_amount_in_words': _amount_to_words(invoice.total_tax or 0),
        'tax_rows': _tax_summary(invoice.items),
    }


def _normalized_owner_name(owner_name):
    return re.sub(r'\s+', ' ', (owner_name or '').strip().lower())


def _format_archive_component(template, invoice_date):
    return template.format(
        year=invoice_date.year,
        month=invoice_date.month,
        month_padded=f"{invoice_date.month:02d}",
        month_name=invoice_date.strftime('%B'),
        month_short=invoice_date.strftime('%b'),
        month_short_upper=invoice_date.strftime('%b').upper(),
        month_short_lower=invoice_date.strftime('%b').lower(),
    )


def _resolve_archive_directory(invoice):
    invoice_date = invoice.date or date.today()
    owner_name = invoice.owner.name if invoice.owner else 'Unknown Owner'
    normalized_owner_name = _normalized_owner_name(owner_name)
    rules = current_app.config.get('INVOICE_ARCHIVE_RULES', [])

    for rule in rules:
        keywords = [_normalized_owner_name(keyword) for keyword in rule.get('owner_keywords', [])]
        if any(keyword and keyword in normalized_owner_name for keyword in keywords):
            year_folder = _format_archive_component(rule.get('year_folder', '{year}'), invoice_date)
            month_folder = _format_archive_component(rule.get('month_folder', '{month_short_upper} {year}'), invoice_date)
            return os.path.join(rule['base_dir'], year_folder, month_folder)

    fallback_root = current_app.config.get('INVOICE_ARCHIVE_ROOT')
    if not fallback_root:
        return None

    owner_folder = sanitize_windows_name(owner_name, default='Unknown Owner')
    return os.path.join(
        fallback_root,
        owner_folder,
        str(invoice_date.year),
        f"{invoice_date.strftime('%b').upper()} {invoice_date.year}",
    )


def _resolve_archive_file_path(invoice):
    archive_dir = _resolve_archive_directory(invoice)
    if not archive_dir:
        return None
    invoice_number = sanitize_windows_name(invoice.invoice_number, default=f"invoice-{invoice.id}")
    customer_name = sanitize_windows_name(invoice.customer.name if invoice.customer else '', default='customer')
    return os.path.join(archive_dir, f"{invoice_number} - {customer_name}.pdf")


def _default_pdf_filename(invoice):
    invoice_number = sanitize_windows_name(invoice.invoice_number, default=f"invoice-{invoice.id}")
    customer_name = sanitize_windows_name(invoice.customer.name if invoice.customer else '', default='customer')
    return f"{invoice_number} - {customer_name}.pdf"


def _normalize_manual_pdf_path(invoice, requested_path):
    requested_path = (requested_path or '').strip()
    if not requested_path:
        raise ValueError('Enter a PDF file path or folder path.')

    normalized_path = os.path.abspath(os.path.expanduser(requested_path))
    if normalized_path.lower().endswith('.pdf'):
        return normalized_path
    return os.path.join(normalized_path, _default_pdf_filename(invoice))


def _write_invoice_pdf(invoice, output_path):
    if not output_path:
        return None

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pdf_bytes = generate_pdf('invoice_pdf.html', _invoice_template_context(invoice))
    with open(output_path, 'wb') as pdf_file:
        pdf_file.write(pdf_bytes)
    return output_path


def _save_invoice_pdf_copy(invoice):
    archive_path = _resolve_archive_file_path(invoice)
    return _write_invoice_pdf(invoice, archive_path)


def _report_date_range(month, year):
    last_day = calendar.monthrange(year, month)[1]
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)
    return start_date, end_date


def _report_period_from_request():
    today = date.today()
    month = request.args.get('month', type=int)
    year = request.args.get('year', type=int)
    owner_id = request.args.get('owner_id', type=int)
    if month is None or year is None or owner_id is None:
        return None, today.month, today.year, owner_id
    if month < 1 or month > 12 or year < 1900 or not db.session.get(Owner, owner_id):
        return None, month, year, owner_id
    return (month, year, owner_id), month, year, owner_id


def _monthly_report_context(month, year, owner_id=None):
    start_date, end_date = _report_date_range(month, year)
    owner = db.session.get(Owner, owner_id) if owner_id else None
    invoice_query = Invoice.query.filter(Invoice.date.between(start_date, end_date))
    if owner:
        invoice_query = invoice_query.filter(Invoice.owner_id == owner.id)
    invoices = invoice_query.order_by(Invoice.date.asc(), Invoice.invoice_number.asc()).all()

    report_rows = []
    summary = {
        'invoice_count': len(invoices),
        'subtotal_total': 0.0,
        'tax_total': 0.0,
        'grand_total': 0.0,
        'paid_total': 0.0,
        'balance_total': 0.0,
    }

    for invoice in invoices:
        total_paid = sum(payment.amount for payment in invoice.payments)
        balance = (invoice.grand_total or 0) - total_paid
        report_rows.append({
            'invoice': invoice,
            'tax_percentage': _report_tax_percentage(invoice),
            'tax_display': _report_tax_display(invoice),
            'total_paid': round(total_paid, 2),
            'balance': round(balance, 2),
        })
        summary['subtotal_total'] += invoice.subtotal_amount or 0
        summary['tax_total'] += invoice.total_tax or 0
        summary['grand_total'] += invoice.grand_total or 0
        summary['paid_total'] += total_paid
        summary['balance_total'] += balance

    for field in summary:
        summary[field] = round(summary[field], 2)

    return {
        'month': month,
        'year': year,
        'month_name': calendar.month_name[month],
        'month_short_lower': calendar.month_abbr[month].lower(),
        'start_date': start_date,
        'end_date': end_date,
        'invoices': invoices,
        'report_rows': report_rows,
        'summary': summary,
        'company': _owner_details(),
        'selected_owner': owner,
        'owner_label': owner.name if owner else 'All Owners',
        'generated_on': date.today(),
        'period_label': f"{calendar.month_name[month]} {year}",
    }


def _report_tax_percentage(invoice):
    subtotal = invoice.subtotal_amount or 0
    total_tax = invoice.total_tax or 0
    if subtotal <= 0 or total_tax <= 0:
        return 0.0
    return round((total_tax / subtotal) * 100, 2)


def _report_tax_display(invoice):
    tax_percentage = _report_tax_percentage(invoice)
    return f"{tax_percentage:.2f}% (₹{(invoice.total_tax or 0):.2f})"


def _report_pdf_filename(month, year):
    return f"sales_{calendar.month_abbr[month].lower()}-{year}.pdf"


def _write_report_pdf(month, year, owner_id=None):
    context = _monthly_report_context(month, year, owner_id)
    return generate_pdf('report_pdf.html', context)


def _next_invoice_number(series, invoice_date, owner_id, exclude_invoice_id=None):
    start_year = invoice_date.year if invoice_date.month >= 4 else invoice_date.year - 1
    end_year = start_year + 1
    year_suffix = f"{str(start_year)[-2:]}-{str(end_year)[-2:]}"
    prefix = f"{series}/"
    suffix = f"/{year_suffix}"
    query = Invoice.query.filter(
        Invoice.owner_id == owner_id,
        Invoice.invoice_number.like(f"{prefix}%{suffix}")
    )
    if exclude_invoice_id:
        query = query.filter(Invoice.id != exclude_invoice_id)
    last_invoice = query.order_by(Invoice.invoice_number.desc()).first()
    next_num = 1
    if last_invoice:
        try:
            next_num = int(last_invoice.invoice_number.split('/')[1]) + 1
        except (IndexError, ValueError):
            next_num = 1
    return f"{prefix}{next_num:04d}{suffix}"


def _render_invoice_form(invoice=None):
    owners = Owner.query.order_by(Owner.name).all()
    customers = Customer.query.order_by(Customer.name).all()
    products = Product.query.order_by(Product.name).all()
    return render_template(
        'invoice_create.html',
        owners=owners,
        customers=customers,
        products=products,
        today=(invoice.date.isoformat() if invoice and invoice.date else date.today().isoformat()),
        invoice=invoice,
    )


def _save_invoice_from_form(invoice=None):
    owners = Owner.query.order_by(Owner.name).all()
    customers = Customer.query.order_by(Customer.name).all()
    products = Product.query.order_by(Product.name).all()
    customer_id = request.form['customer_id']
    customer = Customer.query.get_or_404(customer_id)
    owner_id = request.form.get('owner_id', type=int)
    if not owner_id:
        flash('Select an owner for this invoice.', 'danger')
        return render_template('invoice_create.html', owners=owners, customers=customers, products=products, today=date.today().isoformat(), invoice=invoice)
    Owner.query.get_or_404(owner_id)
    series = request.form.get('series', 'INV')
    invoice_date = date.fromisoformat(request.form.get('invoice_date')) if request.form.get('invoice_date') else date.today()
    descs = request.form.getlist('desc[]')
    hsn_codes = request.form.getlist('hsn_code[]')
    units = request.form.getlist('unit[]')
    qty_inputs = request.form.getlist('qty[]')
    rate_inputs = request.form.getlist('rate[]')
    discount_inputs = request.form.getlist('discount[]')
    cgst_inputs = request.form.getlist('cgst_rate[]')
    sgst_inputs = request.form.getlist('sgst_rate[]')
    igst_inputs = request.form.getlist('igst_rate[]')

    if not descs or not any(desc.strip() for desc in descs):
        flash('Add at least one invoice item.', 'danger')
        return render_template('invoice_create.html', owners=owners, customers=customers, products=products, today=date.today().isoformat(), invoice=invoice)

    try:
        qtys = [float(value or 0) for value in qty_inputs]
        rates = [float(value or 0) for value in rate_inputs]
        disc_percents = [float(value or 0) for value in discount_inputs]
        cgst_rates = [float(value or 0) for value in cgst_inputs]
        sgst_rates = [float(value or 0) for value in sgst_inputs]
        igst_rates = [float(value or 0) for value in igst_inputs]
    except ValueError:
        flash('Invoice item values must be valid numbers.', 'danger')
        return render_template('invoice_create.html', owners=owners, customers=customers, products=products, today=date.today().isoformat(), invoice=invoice)

    if not all(len(values) == len(descs) for values in (hsn_codes, units, qtys, rates, disc_percents, cgst_rates, sgst_rates, igst_rates)):
        flash('Invoice item rows are incomplete. Please review and try again.', 'danger')
        return render_template('invoice_create.html', owners=owners, customers=customers, products=products, today=date.today().isoformat(), invoice=invoice)

    is_new = invoice is None
    if is_new:
        invoice = Invoice(
            series=series,
            invoice_number=_next_invoice_number(series, invoice_date, owner_id),
            status='Pending'
        )
        db.session.add(invoice)

    invoice.series = series
    invoice.po_number = request.form.get('po_number', '').strip()
    invoice.reference_number = request.form.get('reference_number', '').strip()
    invoice.reference_date = date.fromisoformat(request.form.get('reference_date')) if request.form.get('reference_date') else None
    invoice.other_references = request.form.get('other_references', '').strip()
    invoice.date = invoice_date
    invoice.due_date = date.fromisoformat(request.form.get('due_date')) if request.form.get('due_date') else None
    invoice.customer_id = customer_id
    invoice.owner_id = owner_id
    invoice.place_of_supply = customer.state
    invoice.notes = request.form.get('notes', '')
    db.session.flush()

    if not is_new:
        InvoiceItem.query.filter_by(invoice_id=invoice.id).delete()

    subtotal = 0.0
    cgst_tot = sgst_tot = igst_tot = discount_tot = 0.0
    for i in range(len(descs)):
        if not descs[i].strip():
            continue
        item = InvoiceItem(
            invoice_id=invoice.id,
            description=descs[i].strip(),
            hsn_code=hsn_codes[i].strip() if len(hsn_codes) > i else '',
            unit=(units[i].strip() if len(units) > i and units[i].strip() else 'Nos'),
            quantity=qtys[i],
            rate=rates[i],
            discount_percent=disc_percents[i],
            cgst_rate=cgst_rates[i],
            sgst_rate=sgst_rates[i],
            igst_rate=igst_rates[i]
        )
        item_sub = item.quantity * item.rate * (1 - item.discount_percent / 100)
        item_cgst = item_sub * (item.cgst_rate / 100)
        item_sgst = item_sub * (item.sgst_rate / 100)
        item_igst = item_sub * (item.igst_rate / 100)
        item.item_subtotal = round(item_sub, 2)
        item.item_tax = round(item_cgst + item_sgst + item_igst, 2)
        item.item_total = round(item.item_subtotal + item.item_tax, 2)
        db.session.add(item)

        subtotal += item.item_subtotal
        cgst_tot += item_cgst
        sgst_tot += item_sgst
        igst_tot += item_igst
        discount_tot += item.quantity * item.rate * (item.discount_percent / 100)

    invoice.subtotal_amount = round(subtotal, 2)
    invoice.cgst_amount = round(cgst_tot, 2)
    invoice.sgst_amount = round(sgst_tot, 2)
    invoice.igst_amount = round(igst_tot, 2)
    invoice.total_tax = round(cgst_tot + sgst_tot + igst_tot, 2)
    invoice.grand_total = round(subtotal + cgst_tot + sgst_tot + igst_tot, 2)
    invoice.discount_total = round(discount_tot, 2)

    db.session.commit()
    archive_path = None
    try:
        archive_path = _save_invoice_pdf_copy(invoice)
    except Exception as exc:
        current_app.logger.exception('Failed to save invoice PDF copy for invoice %s', invoice.id)
        flash(f'Invoice PDF copy could not be saved: {exc}', 'warning')

    flash(f'Invoice {invoice.invoice_number} {"created" if is_new else "updated"} successfully!', 'success')
    if archive_path:
        flash(f'PDF copy saved to {archive_path}', 'info')
    return redirect(url_for('main.invoice_list'))

# Authentication routes
@main.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('main.dashboard'))
        flash('Invalid username or password', 'danger')
    return render_template('login.html')

@main.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash('Username or email already exists', 'danger')
            return render_template('register.html')
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('main.login'))
    return render_template('register.html')

@main.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully', 'success')
    return redirect(url_for('main.login'))

@main.route('/')
def index():
    return redirect(url_for('main.login'))

# Protected routes
@main.route('/dashboard')
@login_required
def dashboard():
    owner_id = request.args.get('owner_id', type=int)
    invoice_query = Invoice.query
    if owner_id:
        invoice_query = invoice_query.filter(Invoice.owner_id == owner_id)
    stats = {
        'total_invoices': invoice_query.count(),
        'total_customers': Customer.query.count(),
        'total_owners': Owner.query.count(),
        'total_products': Product.query.count(),
        'total_revenue': invoice_query.with_entities(func.sum(Invoice.grand_total)).scalar() or 0,
        'unpaid_invoices': invoice_query.filter(Invoice.status != 'Paid').count(),
        'recent_invoices': invoice_query.order_by(Invoice.date.desc()).limit(10).all(),
    }
    owners = Owner.query.order_by(Owner.name).all()
    selected_owner = Owner.query.get(owner_id) if owner_id else None
    stats['selected_owner'] = selected_owner
    stats['owners'] = owners
    return render_template('dashboard.html', **stats)

@main.route('/invoices')
@login_required
def invoice_list():
    query = Invoice.query.order_by(Invoice.date.desc())
    search = request.args.get('search')
    status = request.args.get('status')
    owner_id = request.args.get('owner_id', type=int)
    if search:
        query = query.filter(or_(Invoice.invoice_number.contains(search), Invoice.customer.has(Customer.name.contains(search))))
    if status:
        query = query.filter_by(status=status)
    if owner_id:
        query = query.filter(Invoice.owner_id == owner_id)
    page = request.args.get('page', 1, type=int)
    pagination = query.paginate(page=page, per_page=20, error_out=False)
    owners = Owner.query.order_by(Owner.name).all()
    return render_template('invoice_list.html', pagination=pagination, owners=owners)

@main.route('/invoice/<int:id>')
@login_required
def invoice_detail(id):
    invoice = Invoice.query.get_or_404(id)
    context = _invoice_template_context(invoice)
    context['archive_path'] = _resolve_archive_file_path(invoice)
    context['default_manual_pdf_path'] = _resolve_archive_file_path(invoice) or _default_pdf_filename(invoice)
    return render_template('invoice_detail.html', **context)

@main.route('/invoice/create', methods=['GET', 'POST'])
@login_required
def invoice_create():
    if request.method == 'POST':
        return _save_invoice_from_form()
    return _render_invoice_form()


@main.route('/invoice/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def invoice_edit(id):
    invoice = Invoice.query.get_or_404(id)
    if request.method == 'POST':
        return _save_invoice_from_form(invoice)
    return _render_invoice_form(invoice)


@main.route('/invoice/<int:id>/save-pdf')
@login_required
def invoice_save_pdf(id):
    invoice = Invoice.query.get_or_404(id)
    try:
        archive_path = _save_invoice_pdf_copy(invoice)
    except Exception as exc:
        current_app.logger.exception('Failed to save invoice PDF copy for invoice %s', invoice.id)
        flash(f'Invoice PDF copy could not be saved: {exc}', 'warning')
        flash('You can still enter a manual PDF path below and try again after PDF generation is available, or use Print Invoice and your browser Print to PDF option.', 'info')
    else:
        flash(f'PDF copy saved to {archive_path}', 'success')
    return redirect(url_for('main.invoice_detail', id=id))


@main.route('/invoice/<int:id>/save-pdf-manual', methods=['POST'])
@login_required
def invoice_save_pdf_manual(id):
    invoice = Invoice.query.get_or_404(id)
    requested_path = request.form.get('manual_pdf_path', '')
    try:
        manual_path = _normalize_manual_pdf_path(invoice, requested_path)
        saved_path = _write_invoice_pdf(invoice, manual_path)
    except ValueError as exc:
        flash(str(exc), 'warning')
    except Exception as exc:
        current_app.logger.exception('Failed to save invoice PDF manually for invoice %s', invoice.id)
        flash(f'Invoice PDF could not be saved to the manual path: {exc}', 'warning')
        flash('If the message mentions missing WeasyPrint libraries, use Print Invoice and choose Save as PDF from the browser print dialog until those libraries are installed.', 'info')
    else:
        flash(f'PDF copy saved to {saved_path}', 'success')
    return redirect(url_for('main.invoice_detail', id=id))

# Customer routes
@main.route('/customers', methods=['GET', 'POST'])
@login_required
def customer_list():
    if request.method == 'POST':
        customer = Customer(
            name=request.form['name'],
            gstin=request.form.get('gstin'),
            state=request.form['state'],
            address=request.form['address'],
            email=request.form.get('email'),
            phone=request.form.get('phone')
        )
        db.session.add(customer)
        db.session.commit()
        flash('Customer added successfully!', 'success')
        return redirect(url_for('main.customer_list'))
    page = request.args.get('page', 1, type=int)
    customers = Customer.query.paginate(page=page, per_page=20, error_out=False)
    return render_template('customers.html', customers=customers)


@main.route('/owners', methods=['GET', 'POST'])
@login_required
def owner_list():
    if request.method == 'POST':
        owner = Owner(
            name=request.form['name'],
            gstin=request.form.get('gstin'),
            phone=request.form.get('phone'),
            state=request.form['state'],
            address=request.form.get('address'),
        )
        db.session.add(owner)
        db.session.commit()
        flash('Owner added successfully!', 'success')
        return redirect(url_for('main.owner_list'))
    page = request.args.get('page', 1, type=int)
    owners = Owner.query.order_by(Owner.name).paginate(page=page, per_page=20, error_out=False)
    return render_template('owners.html', owners=owners)


@main.route('/owner/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def owner_edit(id):
    owner = Owner.query.get_or_404(id)
    if request.method == 'POST':
        owner.name = request.form['name']
        owner.gstin = request.form.get('gstin')
        owner.phone = request.form.get('phone')
        owner.state = request.form['state']
        owner.address = request.form.get('address')
        db.session.commit()
        flash('Owner updated!', 'success')
        return redirect(url_for('main.owner_list'))
    return render_template('owner_form.html', owner=owner)


@main.route('/owner/<int:id>/delete')
@login_required
def owner_delete(id):
    owner = Owner.query.get_or_404(id)
    if owner.invoices:
        flash('Cannot delete owner with invoices.', 'danger')
    else:
        db.session.delete(owner)
        db.session.commit()
        flash('Owner deleted!', 'success')
    return redirect(url_for('main.owner_list'))

@main.route('/customer/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def customer_edit(id):
    customer = Customer.query.get_or_404(id)
    if request.method == 'POST':
        customer.name = request.form['name']
        customer.gstin = request.form['gstin']
        customer.state = request.form['state']
        customer.address = request.form['address']
        customer.email = request.form.get('email')
        customer.phone = request.form.get('phone')
        db.session.commit()
        flash('Customer updated!', 'success')
        return redirect(url_for('main.customer_list'))
    return render_template('edit.html', customer=customer)

@main.route('/customer/<int:id>/delete')
@login_required
def customer_delete(id):
    customer = Customer.query.get_or_404(id)
    if customer.invoices:
        flash('Cannot delete customer with invoices.', 'danger')
    else:
        db.session.delete(customer)
        db.session.commit()
        flash('Customer deleted!', 'success')
    return redirect(url_for('main.customer_list'))

# Product routes
@main.route('/products', methods=['GET', 'POST'])
@login_required
def products():
    if request.method == 'POST':
        product = Product(
            name=request.form['name'],
            hsn_code=request.form.get('hsn_code'),
            rate=float(request.form.get('rate', 0)),
            gst_percent=float(request.form.get('gst_percent', 18.0)),
            stock_qty=float(request.form.get('stock_qty', 0)),
            unit=request.form.get('unit', 'Nos')
        )
        db.session.add(product)
        db.session.commit()
        flash('Product created successfully!', 'success')
        return redirect(url_for('main.products'))
    page = request.args.get('page', 1, type=int)
    products = Product.query.paginate(page=page, per_page=20, error_out=False)
    return render_template('products.html', products=products)

@main.route('/product/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def product_edit(id):
    product = Product.query.get_or_404(id)
    if request.method == 'POST':
        product.name = request.form['name']
        product.hsn_code = request.form.get('hsn_code')
        product.rate = float(request.form.get('rate', 0))
        product.gst_percent = float(request.form.get('gst_percent', 18.0))
        product.stock_qty = float(request.form.get('stock_qty', 0))
        product.unit = request.form.get('unit', 'Nos')
        db.session.commit()
        flash('Product updated!', 'success')
        return redirect(url_for('main.products'))
    return render_template('product_form.html', product=product)

@main.route('/product/<int:id>/delete')
@login_required
def product_delete(id):
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted!', 'success')
    return redirect(url_for('main.products'))

# Reports
@main.route('/reports')
@login_required
def reports():
    report_period, selected_month, selected_year, selected_owner_id = _report_period_from_request()
    report = _monthly_report_context(*report_period) if report_period else None
    owners = Owner.query.order_by(Owner.name).all()
    months = [(month_number, calendar.month_name[month_number]) for month_number in range(1, 13)]
    return render_template(
        'reports.html',
        report=report,
        owners=owners,
        months=months,
        selected_month=selected_month,
        selected_year=selected_year,
        selected_owner_id=selected_owner_id,
    )


@main.route('/reports/pdf')
@login_required
def reports_pdf():
    report_period, selected_month, selected_year, selected_owner_id = _report_period_from_request()
    if not report_period:
        flash('Choose a valid month, year, and owner before downloading the report.', 'danger')
        return redirect(url_for('main.reports'))

    pdf_bytes = _write_report_pdf(selected_month, selected_year, selected_owner_id)
    filename = _report_pdf_filename(selected_month, selected_year)
    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename,
    )

# Status toggle & delete
@main.route('/invoice/<int:id>/status/<status>')
@login_required
def invoice_status(id, status):
    invoice = Invoice.query.get_or_404(id)
    invoice.status = status
    db.session.commit()
    flash(f'Invoice status updated to {status}', 'success')
    return redirect(url_for('main.invoice_detail', id=id))

@main.route('/invoice/<int:id>/delete')
@login_required
def invoice_delete(id):
    invoice = Invoice.query.get_or_404(id)
    db.session.delete(invoice)
    db.session.commit()
    flash('Invoice deleted!', 'success')
    return redirect(url_for('main.invoice_list'))
