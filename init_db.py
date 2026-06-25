from MultipleFiles import create_app
from MultipleFiles.models import db, User, Customer, Product

app = create_app()

with app.app_context():
    db.drop_all()
    db.create_all()
    
    # Create admin user (default: username=admin, password=admin123)
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', email='admin@gstbilling.com')
        admin.set_password('admin123')
        db.session.add(admin)
    
    # Sample customers
    customers_data = [
        ('ABC Traders', '29AACCA1234R1ZA', 'Tamil Nadu', '123 Main St, Chennai', 'abc@traders.com', '9876543210'),
        ('XYZ Enterprises', '33AABCB5678Q2ZB', 'Maharashtra', '456 MG Road, Mumbai', 'xyz@enterprises.com', '8765432109'),
        ('PQR Solutions', '27AACCP9012S3ZC', 'Karnataka', '789 Brigade Road, Bangalore', 'pqr@solutions.com', '7654321098'),
    ]
    
    for name, gstin, state, address, email, phone in customers_data:
        if not Customer.query.filter_by(gstin=gstin).first():
            customer = Customer(name=name, gstin=gstin, state=state, address=address, email=email, phone=phone)
            db.session.add(customer)
    
    # Sample products
    products_data = [
        ('Laptop Dell XPS', '8471', 85000, 18.0),
        ('Office Chair', '9403', 12000, 18.0),
        ('Consulting Services', '9983', 5000, 18.0),
        ('Software License', '4821', 25000, 18.0),
    ]
    
    for name, hsn, rate, gst in products_data:
        if not Product.query.filter_by(name=name).first():
            product = Product(name=name, hsn_code=hsn, rate=rate, gst_percent=gst)
            db.session.add(product)
    
    db.session.commit()
    print("✅ Database initialized with sample data!")
    print("👤 Admin: username='admin' | password='admin123'")
    print("👥 3 sample customers & 4 products created.")

