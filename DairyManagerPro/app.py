from flask import Flask, render_template, request, redirect, session, jsonify
import mysql.connector

app = Flask(__name__)
app.secret_key = "secret123"


# ✅ ONLY ONE before_request (keep this ONE only)
@app.before_request
def check_login():
    if request.endpoint not in ['login', 'register', 'static']:
        if 'user' not in session:
            return redirect('/login')


def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="dairy_db"
    )


# ================= REGISTER =================
@app.route('/register', methods=['GET','POST'])
def register():
    db = get_db()
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
            return "Invalid login"

    return render_template('login.html')


# ================= LOGOUT =================
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ================= PROTECT =================
@app.before_request
def check_login():
    if request.endpoint not in ['login', 'register', 'static']:
        if 'user' not in session:
            return redirect('/login')
        


# ================= DASHBOARD =================
@app.route('/')
def home():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT COUNT(*) FROM farmers")
    farmers = cursor.fetchone()[0]

    cursor.execute("SELECT IFNULL(SUM(qty),0) FROM milk_collection")
    milk = float(cursor.fetchone()[0])

    cursor.execute("SELECT IFNULL(SUM(total_amount),0) FROM payments WHERE status='Paid'")
    paid_amount = float(cursor.fetchone()[0])

    cursor.execute("SELECT IFNULL(SUM(total),0) FROM sales")
    sales = float(cursor.fetchone()[0])

    payments = paid_amount
    profit = sales - paid_amount

    cursor.execute("""
        SELECT MONTH(date), IFNULL(SUM(total),0)
        FROM sales
        GROUP BY MONTH(date)
    """)
    sales_data = [0]*6
    for row in cursor.fetchall():
        month = int(row[0])
        if month <= 6:
            sales_data[month-1] = float(row[1])

    cursor.execute("""
        SELECT MONTH(payment_date), IFNULL(SUM(total_amount),0)
        FROM payments WHERE status='Paid'
        GROUP BY MONTH(payment_date)
    """)
    payment_data = [0]*6
    for row in cursor.fetchall():
        month = int(row[0])
        if month <= 6:
            payment_data[month-1] = float(row[1])

    profit_data = []
    for i in range(6):
        profit_data.append(sales_data[i] - payment_data[i])

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
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']

        # ✅ GET ALL EXISTING CODES
        cursor.execute("SELECT farmer_code FROM farmers")
        codes = cursor.fetchall()

        used = sorted([
            int(c['farmer_code'][1:])
            for c in codes
            if c['farmer_code'] and c['farmer_code'].startswith('F')
        ])

        # ✅ FIND FIRST MISSING NUMBER (START FROM 101)
        new_num = 101
        for num in used:
            if num == new_num:
                new_num += 1
            else:
                break

        farmer_code = f"F{new_num}"

        # ✅ INSERT
        cursor.execute("""
            INSERT INTO farmers(farmer_code,name,phone,status)
            VALUES(%s,%s,%s,'Active')
        """, (farmer_code, name, phone))

        db.commit()

    cursor.execute("SELECT * FROM farmers ORDER BY f_id")
    data = cursor.fetchall()

    return render_template('farmers.html', farmers=data)

# ================= MILK =================
@app.route('/milk', methods=['GET','POST'])
def milk():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        farmer_id = request.form['farmer']
        qty = float(request.form['qty'])
        fat = float(request.form['fat'])
        session = request.form['session']
        date = request.form['date']
        time = request.form['time']

        rate = 25 + (fat * 7)
        amount = qty * rate

        cursor.execute("""
            INSERT INTO milk_collection
            (farmer_id, qty, fat, session, date, time, amount)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (farmer_id, qty, fat, session, date, time, amount))

        db.commit()

    cursor.execute("""
        SELECT m.*, f.name
        FROM milk_collection m
        JOIN farmers f ON m.farmer_id = f.f_id
        ORDER BY m.id DESC
    """)
    data = cursor.fetchall()

    cursor.execute("SELECT * FROM farmers")
    farmers = cursor.fetchall()

    return render_template('milk.html', data=data, farmers=farmers)

# ================= PAYMENTS =================
@app.route('/payments', methods=['GET','POST'])
def payments():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        farmer_id = request.form['farmer']
        amount = float(request.form['amount'])
        status = request.form['status']

        cursor.execute("""
            INSERT INTO payments (farmer_id,total_amount,status,payment_date)
            VALUES (%s,%s,%s,CURDATE())
        """, (farmer_id, amount, status))

        db.commit()

    # ✅ CORRECT QUERY (NO JOIN BUG)
    cursor.execute("""
        SELECT 
            f.f_id,
            f.name,
            f.farmer_code,

            IFNULL((
                SELECT SUM(m.amount)
                FROM milk_collection m
                WHERE m.farmer_id = f.f_id
            ), 0) AS total_milk,

            IFNULL((
                SELECT SUM(p.total_amount)
                FROM payments p
                WHERE p.farmer_id = f.f_id AND p.status='Paid'
            ), 0) AS paid,

            (
                SELECT MAX(p2.payment_date)
                FROM payments p2
                WHERE p2.farmer_id = f.f_id
            ) AS payment_date

        FROM farmers f
    """)

    data = cursor.fetchall()

    # ✅ CALCULATE PENDING
    for row in data:
        total = float(row['total_milk'] or 0)
        paid = float(row['paid'] or 0)
        pending = total - paid
        row['total_amount'] = round(max(pending, 0), 2)

    cursor.execute("SELECT * FROM farmers")
    farmers = cursor.fetchall()

    return render_template('payments.html', data=data, farmers=farmers)



# ================= STOCK =================
@app.route('/stock', methods=['GET','POST'])
def stock():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        cursor.execute("""
            INSERT INTO stock (product_id,product_name,price,quantity,last_updated)
            VALUES (%s,%s,%s,%s,CURDATE())
        """, (
            request.form['product_id'],
            request.form['product_name'],
            float(request.form['price']),
            float(request.form['quantity'])
        ))
        db.commit()

    cursor.execute("SELECT * FROM stock ORDER BY id DESC")
    data = cursor.fetchall()

    return render_template('stock.html', data=data)

# ================= SALES =================
@app.route('/sales', methods=['GET','POST'])
def sales():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        product_id = request.form['product_id']
        quantity = float(request.form['quantity'])

        cursor.execute("SELECT * FROM stock WHERE product_id=%s", (product_id,))
        product = cursor.fetchone()

        if product:
            if quantity > product['quantity']:
                return "Not enough stock!"

            total = product['price'] * quantity

            cursor.execute("""
                INSERT INTO sales (product_id,product_name,price,quantity,total,date)
                VALUES (%s,%s,%s,%s,%s,CURDATE())
            """, (product_id, product['product_name'], product['price'], quantity, total))

            cursor.execute("""
                UPDATE stock SET quantity=%s WHERE product_id=%s
            """, (product['quantity'] - quantity, product_id))

            db.commit()

    cursor.execute("SELECT * FROM sales ORDER BY id DESC")
    data = cursor.fetchall()

    cursor.execute("SELECT * FROM stock")
    products = cursor.fetchall()

    return render_template('sales.html', data=data, products=products)

# ================= HISTORY =================
@app.route('/history', methods=['GET','POST'])
def history():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    selected_date = request.form.get('date')

    if not selected_date:
        from datetime import date
        selected_date = date.today()

    cursor.execute("""
        SELECT m.id, f.name, m.qty, m.fat, m.amount, m.time
        FROM milk_collection m
        JOIN farmers f ON m.farmer_id = f.f_id
        WHERE DATE(m.date)=%s
        ORDER BY m.time ASC
    """, (selected_date,))

    data = cursor.fetchall()

    return render_template('history.html', data=data, selected_date=selected_date)

# ================= PROFIT =================
@app.route('/profit')
def profit():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT IFNULL(SUM(total),0) FROM sales")
    sales = float(cursor.fetchone()[0])

    # ✅ ONLY PAID
    cursor.execute("""
        SELECT IFNULL(SUM(total_amount),0)
        FROM payments
        WHERE status='Paid'
    """)
    payments = float(cursor.fetchone()[0])

    net_profit = sales - payments

    # Monthly sales
    cursor.execute("""
        SELECT MONTH(date), IFNULL(SUM(total),0)
        FROM sales
        GROUP BY MONTH(date)
    """)
    sales_data = [0]*6
    for row in cursor.fetchall():
        m = int(row[0])
        if m <= 6:
            sales_data[m-1] = float(row[1])

    # Monthly PAID payments
    cursor.execute("""
        SELECT MONTH(payment_date), IFNULL(SUM(total_amount),0)
        FROM payments
        WHERE status='Paid'
        GROUP BY MONTH(payment_date)
    """)
    payment_data = [0]*6
    for row in cursor.fetchall():
        m = int(row[0])
        if m <= 6:
            payment_data[m-1] = float(row[1])

    profit_data = []
    for i in range(6):
        profit_data.append(sales_data[i] - payment_data[i])

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
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        cursor.execute("""
            UPDATE farmers SET name=%s, phone=%s WHERE f_id=%s
        """, (request.form['name'], request.form['phone'], id))
        db.commit()
        return redirect('/farmers')

    cursor.execute("SELECT * FROM farmers WHERE f_id=%s", (id,))
    farmer = cursor.fetchone()

    return render_template('edit_farmer.html', farmer=farmer)

@app.route('/delete/<int:id>')
def delete_farmer(id):
    db = get_db()
    cursor = db.cursor()

    # delete related data first
    cursor.execute("DELETE FROM milk_collection WHERE farmer_id=%s", (id,))
    cursor.execute("DELETE FROM payments WHERE farmer_id=%s", (id,))

    # now delete farmer
    cursor.execute("DELETE FROM farmers WHERE f_id=%s", (id,))

    db.commit()
    return redirect('/farmers')

@app.route('/delete_stock/<int:id>')
def delete_stock(id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("DELETE FROM stock WHERE id=%s", (id,))
    db.commit()

    return redirect('/stock')

@app.route('/get_amount/<int:farmer_id>')
def get_amount(farmer_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    # total milk
    cursor.execute("""
        SELECT IFNULL(SUM(amount),0) as total
        FROM milk_collection
        WHERE farmer_id = %s
    """, (farmer_id,))
    total = cursor.fetchone()['total']

    # total paid
    cursor.execute("""
        SELECT IFNULL(SUM(total_amount),0) as paid
        FROM payments
        WHERE farmer_id = %s AND status='Paid'
    """, (farmer_id,))
    paid = cursor.fetchone()['paid']

    amount = float(total) - float(paid)

    return {"amount": round(max(amount, 0), 2)}

@app.route('/edit_stock/<int:id>', methods=['GET','POST'])
def edit_stock(id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        product_name = request.form['product_name']
        price = request.form['price']
        quantity = request.form['quantity']

        cursor.execute("""
            UPDATE stock
            SET product_name=%s, price=%s, quantity=%s
            WHERE id=%s
        """, (product_name, price, quantity, id))

        db.commit()
        return redirect('/stock')

    cursor.execute("SELECT * FROM stock WHERE id=%s", (id,))
    data = cursor.fetchone()

    return render_template('edit_stock.html', data=data)


from flask import session, redirect, url_for


if __name__ == '__main__':
    app.run(debug=True)