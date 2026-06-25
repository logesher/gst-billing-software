from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint
from flask_login import UserMixin
from datetime import date
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Customer(db.Model):
    __tablename__ = 'customer'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    gstin = db.Column(db.String(15))
    state = db.Column(db.String(50), nullable=False)

    invoices = db.relationship('Invoice', backref='customer', lazy=True)


class Owner(db.Model):
    __tablename__ = 'owner'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    gstin = db.Column(db.String(15))
    phone = db.Column(db.String(20))
    state = db.Column(db.String(50), nullable=False)
    address = db.Column(db.Text)

    invoices = db.relationship('Invoice', backref='owner', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    hsn_code = db.Column(db.String(20))
    rate = db.Column(db.Float)
    gst_percent = db.Column(db.Float, default=18.0)
    stock_qty = db.Column(db.Float, default=0.0)
    unit = db.Column(db.String(20), default='Nos')

class Invoice(db.Model):
    __tablename__ = 'invoice'
    __table_args__ = (
        UniqueConstraint('owner_id', 'invoice_number', name='uq_invoice_owner_number'),
    )
    id = db.Column(db.Integer, primary_key=True)
    series = db.Column(db.String(10), default='INV')
    invoice_number = db.Column(db.String(20), nullable=False)
    po_number = db.Column(db.String(100))
    reference_number = db.Column(db.String(100))
    reference_date = db.Column(db.Date)
    other_references = db.Column(db.String(200))
    date = db.Column(db.Date, default=date.today)
    due_date = db.Column(db.Date)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('owner.id'))
    place_of_supply = db.Column(db.String(50))
    subtotal_amount = db.Column(db.Float, default=0.0)
    cgst_amount = db.Column(db.Float, default=0.0)
    sgst_amount = db.Column(db.Float, default=0.0)
    igst_amount = db.Column(db.Float, default=0.0)
    total_tax = db.Column(db.Float, default=0.0)
    grand_total = db.Column(db.Float, default=0.0)
    discount_total = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='Pending')
    notes = db.Column(db.Text)

    items = db.relationship('InvoiceItem', backref='invoice', lazy=True, cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='invoice', lazy=True, cascade='all, delete-orphan')

class InvoiceItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    description = db.Column(db.String(200), nullable=False)
    hsn_code = db.Column(db.String(20))
    unit = db.Column(db.String(20), default='Nos')
    quantity = db.Column(db.Float, nullable=False)
    rate = db.Column(db.Float, nullable=False)
    discount_percent = db.Column(db.Float, default=0.0)
    cgst_rate = db.Column(db.Float, default=0.0)
    sgst_rate = db.Column(db.Float, default=0.0)
    igst_rate = db.Column(db.Float, default=0.0)
    item_subtotal = db.Column(db.Float)
    item_tax = db.Column(db.Float)
    item_total = db.Column(db.Float)

    product = db.relationship('Product')

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, default=date.today)
    method = db.Column(db.String(50), default='Cash')
    reference = db.Column(db.String(100))
    notes = db.Column(db.Text)

