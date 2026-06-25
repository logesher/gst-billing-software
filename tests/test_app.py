import unittest
from datetime import date
import os
import shutil
import uuid

from MultipleFiles import create_app
from MultipleFiles.models import Customer, Invoice, Owner, Product, User, db


class GstBillingAppTests(unittest.TestCase):
    def setUp(self):
        self.archive_dir = os.path.join(os.getcwd(), "instance", f"test_invoice_archive_{uuid.uuid4().hex}")
        os.makedirs(self.archive_dir, exist_ok=True)
        self.app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                "INVOICE_ARCHIVE_ROOT": self.archive_dir,
                "INVOICE_ARCHIVE_RULES": [
                    {
                        "owner_keywords": ["arumugam"],
                        "base_dir": os.path.join(self.archive_dir, "ARUMUGAM BILLS"),
                        "year_folder": "bill {year}",
                        "month_folder": "{month}_{month_short_lower}",
                    },
                    {
                        "owner_keywords": ["pachaiamman", "sri pachaiamman"],
                        "base_dir": os.path.join(self.archive_dir, "PACHAIAMMAN BILLS"),
                        "year_folder": "{year}",
                        "month_folder": "{month_short_upper} {year}",
                    },
                ],
            }
        )
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()
            Owner.query.delete()
            user = User(username="admin", email="admin@example.com")
            user.set_password("secret")
            customer = Customer(
                name="Acme Pvt Ltd",
                gstin="33AAAAA0000A1Z5",
                state="Tamil Nadu",
                address="Chennai",
                email="accounts@acme.test",
                phone="9876543210",
            )
            owner = Owner(
                name="Alpha Traders",
                gstin="33CCCCC0000C1Z7",
                phone="9876501234",
                state="Tamil Nadu",
                address="Madurai",
            )
            second_owner = Owner(
                name="Pachai Traders",
                gstin="33EEEEE0000E1Z9",
                phone="9123456789",
                state="Tamil Nadu",
                address="Salem",
            )
            product = Product(
                name="Widget",
                hsn_code="9983",
                rate=100.0,
                gst_percent=18.0,
                stock_qty=10.0,
                unit="Nos",
            )
            db.session.add_all([user, customer, owner, second_owner, product])
            db.session.commit()
            self.owner_id = owner.id
            self.second_owner_id = second_owner.id
            self.customer_id = customer.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        shutil.rmtree(self.archive_dir, ignore_errors=True)

    def login(self):
        return self.client.post(
            "/main/login",
            data={"username": "admin", "password": "secret"},
            follow_redirects=True,
        )

    def create_invoice(self, invoice_date, description, qty, rate, owner_id=None):
        return self.client.post(
            "/main/invoice/create",
            data={
                "customer_id": "1",
                "owner_id": str(owner_id or self.owner_id),
                "invoice_date": invoice_date,
                "due_date": "2026-04-10",
                "po_number": "PO-7788",
                "reference_number": "REF-2026-01",
                "reference_date": "2026-03-31",
                "other_references": "Transport Copy",
                "desc[]": [description],
                "hsn_code[]": ["9983"],
                "unit[]": ["Kg"],
                "qty[]": [str(qty)],
                "rate[]": [str(rate)],
                "discount[]": ["0"],
                "cgst_rate[]": ["9"],
                "sgst_rate[]": ["9"],
                "igst_rate[]": ["0"],
            },
            follow_redirects=True,
        )

    def test_protected_routes_redirect_to_login(self):
        response = self.client.get("/main/dashboard", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/main/login", response.headers["Location"])

    def test_root_redirects_to_login(self):
        response = self.client.get("/", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/main/login", response.headers["Location"])

    def test_login_dashboard_customers_products_and_reports_load(self):
        self.login()

        for path in (
            "/main/dashboard",
            "/main/customers",
            "/main/owners",
            "/main/products",
            "/main/invoices",
            "/main/invoice/create",
            "/main/reports",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)

    def test_customer_and_product_can_be_created(self):
        self.login()

        customer_response = self.client.post(
            "/main/customers",
            data={
                "name": "Beta Traders",
                "gstin": "32BBBBB0000B1Z6",
                "state": "Kerala",
                "address": "Kochi",
                "email": "beta@example.com",
                "phone": "9999999999",
            },
            follow_redirects=True,
        )
        product_response = self.client.post(
            "/main/products",
            data={
                "name": "Service Plan",
                "hsn_code": "9985",
                "rate": "250",
                "gst_percent": "18",
                "stock_qty": "5",
                "unit": "Nos",
            },
            follow_redirects=True,
        )

        self.assertEqual(customer_response.status_code, 200)
        self.assertEqual(product_response.status_code, 200)
        with self.app.app_context():
            self.assertEqual(Customer.query.count(), 2)
            self.assertEqual(Product.query.count(), 2)

    def test_owner_can_be_created_and_dashboard_invoice_filter_works(self):
        self.login()

        owner_response = self.client.post(
            "/main/owners",
            data={
                "name": "Beta Supplies",
                "gstin": "29DDDDD0000D1Z8",
                "phone": "9000011111",
                "state": "Karnataka",
                "address": "Bengaluru",
            },
            follow_redirects=True,
        )
        self.create_invoice("2026-04-01", "Consulting", 2, 100)

        dashboard_response = self.client.get(f"/main/dashboard?owner_id={self.owner_id}")
        invoice_filter_response = self.client.get(f"/main/invoices?owner_id={self.owner_id}")

        self.assertEqual(owner_response.status_code, 200)
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertEqual(invoice_filter_response.status_code, 200)
        self.assertIn(b"Alpha Traders", dashboard_response.data)
        self.assertIn(b"Alpha Traders", invoice_filter_response.data)
        with self.app.app_context():
            self.assertEqual(Owner.query.count(), 3)

    def test_registration_duplicate_edit_and_delete_flows(self):
        duplicate_response = self.client.post(
            "/main/register",
            data={
                "username": "admin",
                "email": "admin@example.com",
                "password": "secret123",
            },
            follow_redirects=True,
        )
        self.assertEqual(duplicate_response.status_code, 200)
        self.assertIn(b"already exists", duplicate_response.data)

        self.login()
        product_edit = self.client.post(
            "/main/product/1/edit",
            data={
                "name": "Widget X",
                "hsn_code": "9983",
                "rate": "150",
                "gst_percent": "12",
                "stock_qty": "8",
                "unit": "Box",
            },
            follow_redirects=True,
        )
        customer_edit = self.client.post(
            "/main/customer/1/edit",
            data={
                "name": "Acme Updated",
                "gstin": "33AAAAA0000A1Z5",
                "state": "Kerala",
                "address": "Ernakulam",
                "email": "new@acme.test",
                "phone": "9000000000",
            },
            follow_redirects=True,
        )
        product_delete = self.client.get("/main/product/1/delete", follow_redirects=True)
        customer_delete = self.client.get("/main/customer/1/delete", follow_redirects=True)

        self.assertEqual(product_edit.status_code, 200)
        self.assertEqual(customer_edit.status_code, 200)
        self.assertEqual(product_delete.status_code, 200)
        self.assertEqual(customer_delete.status_code, 200)
        with self.app.app_context():
            self.assertEqual(Product.query.count(), 0)
            self.assertEqual(Customer.query.count(), 0)

    def test_invoice_creation_generates_unique_numbers_and_detail_page_renders(self):
        self.login()

        first_response = self.create_invoice("2026-04-01", "Consulting", 2, 100)
        second_response = self.create_invoice("2026-04-02", "Support", 1, 50)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        with self.app.app_context():
            invoices = Invoice.query.order_by(Invoice.id).all()
            self.assertEqual([invoice.invoice_number for invoice in invoices], ["INV/0001/26-27", "INV/0002/26-27"])
            self.assertEqual(invoices[0].grand_total, 236.0)
            self.assertEqual(invoices[1].grand_total, 59.0)
            self.assertEqual(invoices[0].po_number, "PO-7788")
            self.assertEqual(invoices[0].reference_number, "REF-2026-01")
            self.assertEqual(invoices[0].reference_date, date(2026, 3, 31))
            self.assertEqual(invoices[0].other_references, "Transport Copy")
            self.assertEqual(invoices[0].owner.name, "Alpha Traders")
            self.assertEqual(invoices[0].items[0].hsn_code, "9983")
            self.assertEqual(invoices[0].items[0].unit, "Kg")
            invoice_id = invoices[0].id

        detail_response = self.client.get(f"/main/invoice/{invoice_id}")
        expected_pdf = os.path.join(
            self.archive_dir,
            "Alpha Traders",
            "2026",
            "APR 2026",
            "INV-0001-26-27 - Acme Pvt Ltd.pdf",
        )

        self.assertEqual(detail_response.status_code, 200)
        self.assertIn(b"Invoice INV/0001/26-27", detail_response.data)
        self.assertIn(b"Print Invoice", detail_response.data)
        self.assertIn(b"Save PDF Copy", detail_response.data)
        self.assertIn(b"Manual PDF Save Path", detail_response.data)
        self.assertIn(b"Save PDF To This Path", detail_response.data)
        self.assertIn(b"Tax Invoice", detail_response.data)
        self.assertIn(b"PO No.", detail_response.data)
        self.assertIn(b"PO-7788", detail_response.data)
        self.assertIn(b"Reference No. & Date.", detail_response.data)
        self.assertIn(b"REF-2026-01", detail_response.data)
        self.assertIn(b"31-Mar-26", detail_response.data)
        self.assertIn(b"Other References", detail_response.data)
        self.assertIn(b"Transport Copy", detail_response.data)
        self.assertIn(b"Alpha Traders", detail_response.data)
        self.assertIn(b"9983", detail_response.data)
        self.assertIn(b"Kg", detail_response.data)
        self.assertIn(b"Mobile: 9876501234", detail_response.data)
        self.assertTrue(os.path.exists(expected_pdf))

    def test_invoice_pdf_is_saved_in_owner_specific_archive_structure(self):
        self.login()

        with self.app.app_context():
            arumugam = Owner(
                name="Arumugam Owner",
                gstin="33FFFFF0000F1Z1",
                phone="9000012345",
                state="Tamil Nadu",
                address="Madurai",
            )
            pachaiamman = Owner(
                name="Sri Pachaiamman",
                gstin="33GGGGG0000G1Z2",
                phone="9000098765",
                state="Tamil Nadu",
                address="Salem",
            )
            db.session.add_all([arumugam, pachaiamman])
            db.session.commit()
            arumugam_id = arumugam.id
            pachaiamman_id = pachaiamman.id

        march_response = self.create_invoice("2026-03-10", "March Service", 1, 100, owner_id=arumugam_id)
        april_response = self.create_invoice("2026-04-05", "April Service", 1, 100, owner_id=pachaiamman_id)

        self.assertEqual(march_response.status_code, 200)
        self.assertEqual(april_response.status_code, 200)

        march_pdf = os.path.join(
            self.archive_dir,
            "ARUMUGAM BILLS",
            "bill 2026",
            "3_mar",
            "INV-0001-25-26 - Acme Pvt Ltd.pdf",
        )
        april_pdf = os.path.join(
            self.archive_dir,
            "PACHAIAMMAN BILLS",
            "2026",
            "APR 2026",
            "INV-0001-26-27 - Acme Pvt Ltd.pdf",
        )

        self.assertTrue(os.path.exists(march_pdf))
        self.assertTrue(os.path.exists(april_pdf))

    def test_invoice_pdf_can_be_saved_to_manual_path(self):
        self.login()
        self.create_invoice("2026-04-01", "Consulting", 2, 100)

        with self.app.app_context():
            invoice = Invoice.query.first()
            invoice_id = invoice.id

        manual_dir = os.path.join(self.archive_dir, "manual")
        response = self.client.post(
            f"/main/invoice/{invoice_id}/save-pdf-manual",
            data={"manual_pdf_path": manual_dir},
            follow_redirects=True,
        )

        expected_pdf = os.path.join(
            manual_dir,
            "INV-0001-26-27 - Acme Pvt Ltd.pdf",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"PDF copy saved to", response.data)
        self.assertTrue(os.path.exists(expected_pdf))

    def test_monthly_report_page_and_pdf_download_use_selected_period(self):
        self.login()
        self.create_invoice("2026-03-10", "March Service", 1, 100)
        self.create_invoice("2026-04-05", "April Service", 1, 100, owner_id=self.owner_id)
        self.create_invoice("2026-04-12", "Other Owner Service", 1, 100, owner_id=self.second_owner_id)

        report_response = self.client.get(f"/main/reports?month=4&year=2026&owner_id={self.owner_id}")
        pdf_response = self.client.get(f"/main/reports/pdf?month=4&year=2026&owner_id={self.owner_id}")

        self.assertEqual(report_response.status_code, 200)
        self.assertIn(b"Monthly Reports", report_response.data)
        self.assertIn(b"April 2026 - Alpha Traders", report_response.data)
        self.assertIn(b"INV/0001/26-27", report_response.data)
        self.assertIn(b"Amount Without GST", report_response.data)
        self.assertIn(b"18.00%", report_response.data)
        self.assertNotIn(b"Your Company Name", report_response.data)
        self.assertNotIn(b"Generated on:", report_response.data)
        self.assertNotIn(b"March Service", report_response.data)

        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response.mimetype, "application/pdf")
        self.assertIn("sales_apr-2026.pdf", pdf_response.headers["Content-Disposition"])
        self.assertTrue(pdf_response.data.startswith(b"%PDF"))
        self.assertIn(b"18.00%", pdf_response.data)

    def test_invoice_numbering_is_separate_for_each_owner(self):
        self.login()

        self.create_invoice("2026-04-01", "Owner One First", 1, 100, owner_id=self.owner_id)
        self.create_invoice("2026-04-02", "Owner One Second", 1, 100, owner_id=self.owner_id)

        with self.app.app_context():
            existing = Invoice(
                series="INV",
                invoice_number="INV/0005/26-27",
                date=date(2026, 4, 3),
                customer_id=self.customer_id,
                owner_id=self.second_owner_id,
                subtotal_amount=100.0,
                cgst_amount=9.0,
                sgst_amount=9.0,
                total_tax=18.0,
                grand_total=118.0,
                status="Pending",
            )
            db.session.add(existing)
            db.session.commit()

        third_response = self.create_invoice("2026-04-04", "Owner Two Next", 1, 100, owner_id=self.second_owner_id)

        self.assertEqual(third_response.status_code, 200)
        with self.app.app_context():
            owner_one_numbers = [i.invoice_number for i in Invoice.query.filter_by(owner_id=self.owner_id).order_by(Invoice.id).all()]
            owner_two_numbers = [i.invoice_number for i in Invoice.query.filter_by(owner_id=self.second_owner_id).order_by(Invoice.id).all()]
            self.assertEqual(owner_one_numbers, ["INV/0001/26-27", "INV/0002/26-27"])
            self.assertEqual(owner_two_numbers, ["INV/0005/26-27", "INV/0006/26-27"])

    def test_existing_invoice_can_be_edited(self):
        self.login()
        self.create_invoice("2026-04-01", "Consulting", 2, 100)

        with self.app.app_context():
            invoice = Invoice.query.first()
            invoice_id = invoice.id
            original_number = invoice.invoice_number

        edit_response = self.client.post(
            f"/main/invoice/{invoice_id}/edit",
            data={
                "customer_id": str(self.customer_id),
                "owner_id": str(self.owner_id),
                "series": "INV",
                "invoice_date": "2026-04-01",
                "due_date": "2026-04-15",
                "po_number": "PO-9999",
                "reference_number": "REF-EDIT-02",
                "reference_date": "2026-04-01",
                "other_references": "Revised Dispatch Copy",
                "desc[]": ["Updated Service"],
                "hsn_code[]": ["9988"],
                "unit[]": ["Units"],
                "qty[]": ["3"],
                "rate[]": ["200"],
                "discount[]": ["0"],
                "cgst_rate[]": ["9"],
                "sgst_rate[]": ["9"],
                "igst_rate[]": ["0"],
            },
            follow_redirects=True,
        )

        self.assertEqual(edit_response.status_code, 200)
        with self.app.app_context():
            updated = Invoice.query.get(invoice_id)
            self.assertEqual(updated.invoice_number, original_number)
            self.assertEqual(updated.po_number, "PO-9999")
            self.assertEqual(updated.reference_number, "REF-EDIT-02")
            self.assertEqual(updated.reference_date, date(2026, 4, 1))
            self.assertEqual(updated.other_references, "Revised Dispatch Copy")
            self.assertEqual(updated.items[0].description, "Updated Service")
            self.assertEqual(updated.items[0].hsn_code, "9988")
            self.assertEqual(updated.items[0].unit, "Units")
            self.assertEqual(updated.grand_total, 708.0)

    def test_invoice_status_and_customer_delete_guard(self):
        self.login()
        self.create_invoice("2026-04-01", "Consulting", 2, 100)

        with self.app.app_context():
            invoice = Invoice.query.first()
            invoice_id = invoice.id
            customer_id = invoice.customer_id

        status_response = self.client.get(f"/main/invoice/{invoice_id}/status/Paid", follow_redirects=True)
        guarded_delete = self.client.get(f"/main/customer/{customer_id}/delete", follow_redirects=True)

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(guarded_delete.status_code, 200)
        self.assertIn(b"Cannot delete customer with invoices.", guarded_delete.data)
        with self.app.app_context():
            self.assertEqual(Invoice.query.first().status, "Paid")
            self.assertEqual(Customer.query.count(), 1)

    def test_invoice_create_rejects_missing_items(self):
        self.login()
        response = self.client.post(
            "/main/invoice/create",
            data={
                "customer_id": "1",
                "owner_id": str(self.owner_id),
                "invoice_date": "2026-04-01",
                "due_date": "2026-04-10",
                "desc[]": [""],
                "hsn_code[]": ["9983"],
                "unit[]": ["Nos"],
                "qty[]": ["1"],
                "rate[]": ["100"],
                "discount[]": ["0"],
                "cgst_rate[]": ["9"],
                "sgst_rate[]": ["9"],
                "igst_rate[]": ["0"],
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Add at least one invoice item.", response.data)
        with self.app.app_context():
            self.assertEqual(Invoice.query.count(), 0)


if __name__ == "__main__":
    unittest.main()
