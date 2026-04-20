from flask import Flask, render_template, request, redirect, session, jsonify
import mysql.connector
from mysql.connector import Error
import os

app = Flask(__name__)
app.secret_key = "secret123"


def get_db():
    try:
        return mysql.connector.connect(
            host=os.getenv("MYSQLHOST"),
            user=os.getenv("MYSQLUSER"),
            password=os.getenv("MYSQLPASSWORD"),
            database=os.getenv("MYSQLDATABASE"),
            port=int(os.getenv("MYSQLPORT") or 3306)
        )
    except Exception as e:
        print("DB ERROR:", e)
        return None


@app.before_request
def check_login():
    if request.endpoint not in ['login', 'register', 'static']:
        if 'user' not in session:
            return redirect('/login')


# ================= REGISTER =================
@app.route('/register', methods=['GET','POST'])
def register():
    db = get_db()
    if db is None:
        return "Database not connected"
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        phone = request.form.get('phone')
        password = request.form.get('password')

        if not phone or not password:
            return "Missing data"

        cursor.execute("SELECT * FROM manager WHERE phone=%s", (phone,))
        existing = cursor.fetchone()

        if existing:
            return "User already exists"

        cursor.execute(
            "INSERT INTO manager (phone, password) VALUES (%s,%s)",
            (phone, password)
        )
        db.commit()

        return redirect('/login')

    return render_template('register.html')


# ================= LOGIN =================
@app.route('/login', methods=['GET','POST'])
def login():
    db = get_db()
    if db is None:
        return "Database not connected"

    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        phone = request.form['phone']
        password = request.form['password']

        cursor.execute(
            "SELECT * FROM manager WHERE phone=%s AND password=%s",
            (phone, password)
        )
        user = cursor.fetchone()

        if user:
            session['user'] = user['phone']
            return redirect('/')
        else:
            return render_template('login.html', error="Invalid phone or password")

    return render_template('login.html')


# ================= LOGOUT =================
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ================= DASHBOARD =================
@app.route('/')
def home():
    if 'user' not in session:
        return redirect('/login')

    db = get_db()
    if db is None:
        return "Database not connected"

    cursor = db.cursor(dictionary=True)
    user = session.get('user')

    # ================= FARMERS =================
    cursor.execute("""
        SELECT COUNT(*) as total 
        FROM farmers 
        WHERE user_phone=%s
    """, (user,))
    farmers = cursor.fetchone()['total']

    # ================= MILK =================
    cursor.execute("""
        SELECT IFNULL(SUM(qty),0) as total 
        FROM milk_collection 
        WHERE user_phone=%s
    """, (user,))
    milk = float(cursor.fetchone()['total'])

    # ================= PAYMENTS =================
    cursor.execute("""
        SELECT IFNULL(SUM(total_amount),0) as total 
        FROM payments 
        WHERE user_phone=%s
    """, (user,))
    payments = float(cursor.fetchone()['total'])

    # ================= SALES =================
    cursor.execute("""
        SELECT IFNULL(SUM(total),0) as total 
        FROM sales 
        WHERE user_phone=%s
    """, (user,))
    sales = float(cursor.fetchone()['total'])

    profit = sales - payments

    # ================= MONTHLY SALES =================
    cursor.execute("""
        SELECT MONTH(date) as m, IFNULL(SUM(total),0) as total
        FROM sales
        WHERE user_phone=%s
        GROUP BY MONTH(date)
    """, (user,))
    
    sales_data = [0]*6
    for row in cursor.fetchall():
        if row['m'] and 1 <= row['m'] <= 6:
            sales_data[row['m']-1] = float(row['total'])

    # ================= MONTHLY PAYMENTS =================
    cursor.execute("""
        SELECT MONTH(payment_date) as m, IFNULL(SUM(total_amount),0) as total
        FROM payments
        WHERE user_phone=%s
        GROUP BY MONTH(payment_date)
    """, (user,))
    
    payment_data = [0]*6
    for row in cursor.fetchall():
        if row['m'] and 1 <= row['m'] <= 6:
            payment_data[row['m']-1] = float(row['total'])

    # ================= PROFIT =================
    profit_data = [sales_data[i] - payment_data[i] for i in range(6)]

    return render_template(
        'index.html',
        farmers=farmers,
        milk=milk,
        payments=payments,
        sales=sales,
        profit=profit,
        sales_data=sales_data,
        profit_data=profit_data
    )


# ================= FARMERS =================
@app.route('/farmers', methods=['GET','POST'])
def farmers():
    db = get_db()
    if db is None:
        return "Database not connected"

    cursor = db.cursor(dictionary=True)
    user = session.get('user')

    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']

        # ✅ ONLY GET THIS USER'S FARMER CODES
        cursor.execute("""
            SELECT farmer_code FROM farmers 
            WHERE user_phone=%s
        """, (user,))
        codes = cursor.fetchall()

        used = sorted([
            int(c['farmer_code'][1:])
            for c in codes
            if c['farmer_code'] and c['farmer_code'].startswith('F')
        ])

        new_num = 101
        for num in used:
            if num == new_num:
                new_num += 1
            else:
                break

        farmer_code = f"F{new_num}"

        # ✅ INSERT WITH USER
        cursor.execute("""
            INSERT INTO farmers (farmer_code, name, phone, status, user_phone)
            VALUES (%s,%s,%s,'Active',%s)
        """, (farmer_code, name, phone, user))

        db.commit()

    # ✅ LOAD ONLY THIS USER'S FARMERS
    cursor.execute("""
        SELECT * FROM farmers 
        WHERE user_phone=%s
        ORDER BY f_id
    """, (user,))
    data = cursor.fetchall()

    return render_template('farmers.html', farmers=data)


# ================= MILK =================
@app.route('/milk', methods=['GET','POST'])
def milk():
    db = get_db()
    if db is None:
        return "Database not connected"

    cursor = db.cursor(dictionary=True)
    user = session.get('user')

    if request.method == 'POST':
        farmer_id = request.form['farmer']
        qty = float(request.form['qty'])
        fat = float(request.form['fat'])
        session_type = request.form['session']
        date = request.form['date']
        time = request.form['time']

        rate = 25 + (fat * 7)
        amount = qty * rate

        # ✅ INSERT WITH USER
        cursor.execute("""
            INSERT INTO milk_collection
            (farmer_id, qty, fat, session, date, time, amount, user_phone)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (farmer_id, qty, fat, session_type, date, time, amount, user))

        db.commit()

    # ✅ LOAD ONLY THIS USER'S DATA
    cursor.execute("""
        SELECT m.*, f.name
        FROM milk_collection m
        JOIN farmers f ON m.farmer_id = f.f_id
        WHERE m.user_phone=%s
        ORDER BY m.id DESC
    """, (user,))
    data = cursor.fetchall()

    # ✅ LOAD ONLY THIS USER'S FARMERS
    cursor.execute("""
        SELECT * FROM farmers 
        WHERE user_phone=%s
    """, (user,))
    farmers = cursor.fetchall()

    return render_template('milk.html', data=data, farmers=farmers)

# ================= PAYMENTS =================
@app.route('/payments', methods=['GET','POST'])
def payments():
    db = get_db()
    if db is None:
        return "Database not connected"

    cursor = db.cursor(dictionary=True)
    user = session.get('user')

    # ================= INSERT =================
    if request.method == 'POST':
        farmer_id = request.form['farmer']
        amount = float(request.form['amount'])
        status = request.form['status']

        # ✅ INSERT WITH USER
        cursor.execute("""
            INSERT INTO payments 
            (farmer_id, total_amount, status, payment_date, user_phone)
            VALUES (%s,%s,%s,CURDATE(),%s)
        """, (farmer_id, amount, status, user))

        db.commit()

    # ================= SUMMARY =================
    cursor.execute("""
        SELECT 
            f.f_id,
            f.name,
            f.farmer_code,

            IFNULL((
                SELECT SUM(m.amount)
                FROM milk_collection m
                WHERE m.farmer_id = f.f_id 
                AND m.user_phone=%s
            ), 0) AS total_milk,

            IFNULL((
                SELECT SUM(p.total_amount)
                FROM payments p
                WHERE p.farmer_id = f.f_id 
                AND p.status='Paid'
                AND p.user_phone=%s
            ), 0) AS paid,

            (
                SELECT MAX(p2.payment_date)
                FROM payments p2
                WHERE p2.farmer_id = f.f_id
                AND p2.user_phone=%s
            ) AS payment_date

        FROM farmers f
        WHERE f.user_phone=%s
    """, (user, user, user, user))

    data = cursor.fetchall()

    # ================= CALCULATE PENDING =================
    for row in data:
        total = float(row['total_milk'] or 0)
        paid = float(row['paid'] or 0)
        pending = total - paid
        row['total_amount'] = round(max(pending, 0), 2)

    # ================= FARMERS DROPDOWN =================
    cursor.execute("""
        SELECT * FROM farmers 
        WHERE user_phone=%s
    """, (user,))
    farmers = cursor.fetchall()

    return render_template('payments.html', data=data, farmers=farmers)

# ================= STOCK =================
@app.route('/stock', methods=['GET','POST'])
def stock():
    db = get_db()
    if db is None:
        return "Database not connected"

    cursor = db.cursor(dictionary=True)
    user = session.get('user')

    if request.method == 'POST':
        try:
            product_id = request.form.get('product_id')
            product_name = request.form.get('product_name')
            price = float(request.form.get('price') or 0)
            quantity = float(request.form.get('quantity') or 0)

            # ✅ INSERT WITH USER
            cursor.execute("""
                INSERT INTO stock 
                (product_id, product_name, price, quantity, last_updated, user_phone)
                VALUES (%s,%s,%s,%s,CURDATE(),%s)
            """, (product_id, product_name, price, quantity, user))

            db.commit()

        except Exception as e:
            print("STOCK ERROR:", e)
            return "Error adding stock"

    # ✅ LOAD ONLY USER DATA
    cursor.execute("""
        SELECT * FROM stock 
        WHERE user_phone=%s
        ORDER BY last_updated DESC
    """, (user,))
    data = cursor.fetchall()

    return render_template('stock.html', data=data)


# ================= SALES =================
@app.route('/sales', methods=['GET','POST'])
def sales():
    db = get_db()
    if db is None:
        return "Database not connected"

    cursor = db.cursor(dictionary=True)
    user = session.get('user')

    error = None
    success = None

    if request.method == 'POST':
        try:
            product_id = request.form.get('product_id')
            quantity = float(request.form.get('quantity') or 0)

            if not product_id or quantity <= 0:
                error = "Invalid input"

            else:
                # ✅ GET PRODUCT (USER FILTER)
                cursor.execute("""
                    SELECT * FROM stock 
                    WHERE product_id=%s AND user_phone=%s
                """, (product_id, user))
                product = cursor.fetchone()

                if not product:
                    error = "Product not found"

                elif quantity > float(product['quantity']):
                    error = f"Only {product['quantity']} items available!"

                else:
                    total = float(product['price']) * quantity

                    # ✅ INSERT SALE (WITH USER)
                    cursor.execute("""
                        INSERT INTO sales
                        (product_id, product_name, price, quantity, total, date, user_phone)
                        VALUES (%s,%s,%s,%s,%s,CURDATE(),%s)
                    """, (
                        product_id,
                        product['product_name'],
                        product['price'],
                        quantity,
                        total,
                        user
                    ))

                    # ✅ UPDATE STOCK (USER FILTER)
                    cursor.execute("""
                        UPDATE stock 
                        SET quantity=%s 
                        WHERE product_id=%s AND user_phone=%s
                    """, (
                        float(product['quantity']) - quantity,
                        product_id,
                        user
                    ))

                    db.commit()
                    success = "Sale completed successfully!"

        except Exception as e:
            print("SALES ERROR:", e)
            error = "Something went wrong"

    # ✅ LOAD SALES (USER ONLY)
    cursor.execute("""
        SELECT * FROM sales 
        WHERE user_phone=%s 
        ORDER BY id DESC
    """, (user,))
    data = cursor.fetchall()

    # ✅ LOAD PRODUCTS (USER ONLY)
    cursor.execute("""
        SELECT * FROM stock 
        WHERE user_phone=%s
    """, (user,))
    products = cursor.fetchall()

    return render_template(
        'sales.html',
        data=data,
        products=products,
        error=error,
        success=success
    )

# ================= HISTORY =================
@app.route('/history', methods=['GET','POST'])
def history():
    db = get_db()
    if db is None:
        return "Database not connected"
    cursor = db.cursor(dictionary=True)

    user = session.get('user')

    selected_date = request.form.get('date')

    if not selected_date:
        from datetime import date
        selected_date = date.today()

    cursor.execute("""
        SELECT m.id, f.name, m.qty, m.fat, m.amount, m.time
        FROM milk_collection m
        JOIN farmers f ON m.farmer_id = f.f_id
        WHERE DATE(m.date)=%s AND m.user_phone=%s
        ORDER BY m.time ASC
    """, (selected_date, user))

    data = cursor.fetchall()

    return render_template('history.html', data=data, selected_date=selected_date)


# ================= PROFIT =================
@app.route('/profit')
def profit():
    db = get_db()
    if db is None:
        return "Database not connected"

    cursor = db.cursor(dictionary=True)
    user = session.get('user')

    # Total sales
    cursor.execute("""
        SELECT IFNULL(SUM(total),0) as total 
        FROM sales 
        WHERE user_phone=%s
    """, (user,))
    sales = float(cursor.fetchone()['total'] or 0)

    # Total payments
    cursor.execute("""
        SELECT IFNULL(SUM(total_amount),0) as total
        FROM payments
        WHERE user_phone=%s
    """, (user,))
    payments = float(cursor.fetchone()['total'] or 0)

    net_profit = sales - payments

    # Monthly sales
    cursor.execute("""
        SELECT MONTH(date) as m, IFNULL(SUM(total),0) as total
        FROM sales
        WHERE user_phone=%s
        GROUP BY MONTH(date)
    """, (user,))
    sales_data = [0]*6
    for row in cursor.fetchall():
        if row['m'] is not None and row['m'] <= 6:
            sales_data[row['m']-1] = float(row['total'])

    # Monthly payments
    cursor.execute("""
        SELECT MONTH(payment_date) as m, IFNULL(SUM(total_amount),0) as total
        FROM payments
        WHERE user_phone=%s
        GROUP BY MONTH(payment_date)
    """, (user,))
    payment_data = [0]*6
    for row in cursor.fetchall():
        if row['m'] is not None and row['m'] <= 6:
            payment_data[row['m']-1] = float(row['total'])

    profit_data = [sales_data[i] - payment_data[i] for i in range(6)]

    return render_template(
        'profit.html',
        sales=sales,
        payments=payments,
        net_profit=net_profit,
        sales_data=sales_data,
        profit_data=profit_data
    )

@app.route('/edit/<int:id>', methods=['GET','POST'])
def edit_farmer(id):
    db = get_db()
    if db is None:
        return "Database not connected"
    cursor = db.cursor(dictionary=True)

    user = session.get('user')

    if request.method == 'POST':
        cursor.execute("""
            UPDATE farmers 
            SET name=%s, phone=%s 
            WHERE f_id=%s AND user_phone=%s
        """, (request.form['name'], request.form['phone'], id, user))
        db.commit()
        return redirect('/farmers')

    cursor.execute("""
        SELECT * FROM farmers 
        WHERE f_id=%s AND user_phone=%s
    """, (id, user))
    farmer = cursor.fetchone()

    return render_template('edit_farmer.html', farmer=farmer)


@app.route('/delete/<int:id>')
def delete_farmer(id):
    db = get_db()
    if db is None:
        return "Database not connected"
    cursor = db.cursor()

    user = session.get('user')

    cursor.execute("""
        DELETE FROM milk_collection 
        WHERE farmer_id=%s AND user_phone=%s
    """, (id, user))

    cursor.execute("""
        DELETE FROM payments 
        WHERE farmer_id=%s AND user_phone=%s
    """, (id, user))

    cursor.execute("""
        DELETE FROM farmers 
        WHERE f_id=%s AND user_phone=%s
    """, (id, user))

    db.commit()
    return redirect('/farmers')


@app.route('/delete_stock/<string:product_id>')
def delete_stock(product_id):
    db = get_db()
    cursor = db.cursor()
    user = session.get('user')

    cursor.execute("""
        DELETE FROM stock 
        WHERE product_id=%s AND user_phone=%s
    """, (product_id, user))

    db.commit()
    return redirect('/stock')


@app.route('/get_amount/<int:farmer_id>')
def get_amount(farmer_id):
    db = get_db()
    if db is None:
        return {"amount": 0}
    cursor = db.cursor(dictionary=True)

    user = session.get('user')

    cursor.execute("""
        SELECT IFNULL(SUM(amount),0) as total
        FROM milk_collection
        WHERE farmer_id=%s AND user_phone=%s
    """, (farmer_id, user))
    total = cursor.fetchone()['total']

    cursor.execute("""
        SELECT IFNULL(SUM(total_amount),0) as paid
        FROM payments
        WHERE farmer_id=%s AND status='Paid' AND user_phone=%s
    """, (farmer_id, user))
    paid = cursor.fetchone()['paid']

    amount = float(total) - float(paid)

    return {"amount": round(max(amount, 0), 2)}


@app.route('/edit_stock/<string:product_id>', methods=['GET','POST'])
def edit_stock(product_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    user = session.get('user')

    cursor.execute("""
        SELECT * FROM stock 
        WHERE product_id=%s AND user_phone=%s
    """, (product_id, user))
    data = cursor.fetchone()

    if not data:
        return "Product not found"

    if request.method == 'POST':
        product_name = request.form.get('product_name')
        price = float(request.form.get('price') or 0)
        quantity = float(request.form.get('quantity') or 0)

        cursor.execute("""
            UPDATE stock
            SET product_name=%s, price=%s, quantity=%s
            WHERE product_id=%s AND user_phone=%s
        """, (product_name, price, quantity, product_id, user))

        db.commit()
        return redirect('/stock')

    return render_template('edit_stock.html', data=data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)