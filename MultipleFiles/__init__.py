from flask import Flask, redirect, url_for
from flask_login import LoginManager
from .models import db, User
from sqlalchemy import text
import os


def _ensure_invoice_schema():
    columns = {
        row[1]
        for row in db.session.execute(text("PRAGMA table_info(invoice)")).fetchall()
    }
    if "po_number" not in columns:
        db.session.execute(text("ALTER TABLE invoice ADD COLUMN po_number VARCHAR(100)"))
    if "reference_number" not in columns:
        db.session.execute(text("ALTER TABLE invoice ADD COLUMN reference_number VARCHAR(100)"))
    if "reference_date" not in columns:
        db.session.execute(text("ALTER TABLE invoice ADD COLUMN reference_date DATE"))
    if "other_references" not in columns:
        db.session.execute(text("ALTER TABLE invoice ADD COLUMN other_references VARCHAR(200)"))
    if "owner_id" not in columns:
        db.session.execute(text("ALTER TABLE invoice ADD COLUMN owner_id INTEGER"))
    db.session.commit()


def _ensure_invoice_unique_per_owner():
    indexes = db.session.execute(text("PRAGMA index_list(invoice)")).fetchall()
    index_names = {row[1] for row in indexes}

    has_old_global_unique = "sqlite_autoindex_invoice_1" in index_names
    has_owner_unique = any(row[1] == "uq_invoice_owner_number" for row in indexes)

    if has_owner_unique and not has_old_global_unique:
        return

    db.session.execute(text("PRAGMA foreign_keys=OFF"))
    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS invoice__new (
                id INTEGER PRIMARY KEY,
                series VARCHAR(10),
                invoice_number VARCHAR(20) NOT NULL,
                po_number VARCHAR(100),
                reference_number VARCHAR(100),
                reference_date DATE,
                other_references VARCHAR(200),
                date DATE,
                due_date DATE,
                customer_id INTEGER NOT NULL,
                owner_id INTEGER,
                place_of_supply VARCHAR(50),
                subtotal_amount FLOAT,
                cgst_amount FLOAT,
                sgst_amount FLOAT,
                igst_amount FLOAT,
                total_tax FLOAT,
                grand_total FLOAT,
                discount_total FLOAT,
                status VARCHAR(20),
                notes TEXT,
                FOREIGN KEY(customer_id) REFERENCES customer (id),
                FOREIGN KEY(owner_id) REFERENCES owner (id),
                CONSTRAINT uq_invoice_owner_number UNIQUE (owner_id, invoice_number)
            )
            """
        )
    )
    db.session.execute(
        text(
            """
            INSERT INTO invoice__new (
                id, series, invoice_number, po_number, reference_number, reference_date, other_references, date, due_date, customer_id, owner_id,
                place_of_supply, subtotal_amount, cgst_amount, sgst_amount, igst_amount,
                total_tax, grand_total, discount_total, status, notes
            )
            SELECT
                id, series, invoice_number, po_number, reference_number, reference_date, other_references, date, due_date, customer_id, owner_id,
                place_of_supply, subtotal_amount, cgst_amount, sgst_amount, igst_amount,
                total_tax, grand_total, discount_total, status, notes
            FROM invoice
            """
        )
    )
    db.session.execute(text("DROP TABLE invoice"))
    db.session.execute(text("ALTER TABLE invoice__new RENAME TO invoice"))
    db.session.execute(text("PRAGMA foreign_keys=ON"))
    db.session.commit()


def _ensure_invoice_item_schema():
    columns = {
        row[1]
        for row in db.session.execute(text("PRAGMA table_info(invoice_item)")).fetchall()
    }
    if "unit" not in columns:
        db.session.execute(text("ALTER TABLE invoice_item ADD COLUMN unit VARCHAR(20) DEFAULT 'Nos'"))
        db.session.commit()


def _ensure_owner_schema():
    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS owner (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                gstin VARCHAR(15),
                phone VARCHAR(20),
                state VARCHAR(50) NOT NULL,
                address TEXT
            )
            """
        )
    )
    owner_columns = {
        row[1]
        for row in db.session.execute(text("PRAGMA table_info(owner)")).fetchall()
    }
    if "phone" not in owner_columns:
        db.session.execute(text("ALTER TABLE owner ADD COLUMN phone VARCHAR(20)"))
        db.session.commit()
    has_owner = db.session.execute(text("SELECT COUNT(*) FROM owner")).scalar() or 0
    if not has_owner:
        db.session.execute(
            text(
                """
                INSERT INTO owner (name, gstin, phone, state, address)
                VALUES (:name, :gstin, :phone, :state, :address)
                """
            ),
            {
                "name": "Your Company Name",
                "gstin": "GSTIN Number",
                "phone": "",
                "state": "Tamil Nadu",
                "address": "Company Address, City",
            },
        )
        db.session.commit()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='a3c94b802eb54f1fbb94df0a2e6c4fc2',
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{os.path.join(app.instance_path, 'gst_billing.db')}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        COMPANY_NAME='Your Company Name',
        COMPANY_ADDRESS='Company Address',
        COMPANY_CITY='City',
        COMPANY_GSTIN='GSTIN Number',
        COMPANY_STATE='Tamil Nadu',
        COMPANY_STATE_CODE='33',
        COMPANY_PHONE='',
        COMPANY_EMAIL='',
        COMPANY_IRN='',
        COMPANY_ACK_NO='',
        COMPANY_ACK_DATE='',
        INVOICE_ARCHIVE_ROOT=r'D:\appa\ARUMUGAM OFFICE',
        INVOICE_ARCHIVE_RULES=[
            {
                'owner_keywords': ['arumugam'],
                'base_dir': r'D:\appa\ARUMUGAM OFFICE\ARUMUGAM BILLS',
                'year_folder': 'bill {year}',
                'month_folder': '{month}_{month_short_lower}',
            },
            {
                'owner_keywords': ['pachaiamman', 'sri pachaiamman'],
                'base_dir': r'D:\appa\ARUMUGAM OFFICE\PACHAIAMMAN BILLS',
                'year_folder': '{year}',
                'month_folder': '{month_short_upper} {year}',
            },
        ],
    )

    if test_config:
        app.config.update(test_config)

    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    db.init_app(app)

    with app.app_context():
        db.create_all()
        _ensure_owner_schema()
        _ensure_invoice_schema()
        _ensure_invoice_unique_per_owner()
        _ensure_invoice_item_schema()

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from .routes import main
    app.register_blueprint(main, url_prefix='/main')

    @app.route('/')
    def home():
        return redirect(url_for('main.login'))

    return app

