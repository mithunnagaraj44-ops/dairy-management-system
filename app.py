from flask import Flask, render_template, request, redirect, session, jsonify
import mysql.connector
import os

app = Flask(__name__)
app.secret_key = "secret123"


# ================= DATABASE =================
def get_db():
    try:
        return mysql.connector.connect(
            host=os.getenv("MYSQLHOST"),
            user=os.getenv("MYSQLUSER"),
            password=os.getenv("MYSQLPASSWORD"),
            database=os.getenv("MYSQLDATABASE"),
            port=int(os.getenv("MYSQLPORT") or 3306),
            connection_timeout=10
        )
    except Exception as e:
        print("DB ERROR:", e)
        return None


# ================= LOGIN CHECK =================
@app.before_request
def check_login():
    if request.endpoint not in ['login', 'register', 'static']:
        if 'user' not in session:
            return redirect('/login')


# ================= REGISTER =================
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

        # CHECK EXISTING USER
        cursor.execute("""
            SELECT * FROM manager
            WHERE phone=%s
            AND status != 'rejected'
        """, (phone,))

        existing_user = cursor.fetchone()

        # USER ALREADY EXISTS
        if existing_user:

            cursor.close()
            db.close()

            return render_template(
                'register.html',
                message="User already exists"
            )

        # REMOVE OLD REJECTED ACCOUNT
        cursor.execute("""
            DELETE FROM manager
            WHERE phone=%s
            AND status='rejected'
        """, (phone,))

        # INSERT NEW PENDING ACCOUNT
        cursor.execute("""
            INSERT INTO manager (phone, password, status)
            VALUES (%s,%s,'pending')
        """, (phone, password))

        db.commit()

        cursor.close()
        db.close()

        return render_template(
            'register.html',
            message="Registration submitted. Waiting for proprietor approval."
        )

    cursor.close()
    db.close()

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

        cursor.close()
        db.close()

        # ================= USER FOUND =================
        if user:

            # APPROVED
            if user['status'] == 'approved':

                session['user'] = user['phone']
                return redirect('/')

            # PENDING
            elif user['status'] == 'pending':

                return render_template(
                    'login.html',
                    error="Waiting for proprietor approval"
                )

            # REJECTED
            else:

                return render_template(
                    'login.html',
                    error="Account rejected"
                )

        # INVALID LOGIN
        else:

            return render_template(
                'login.html',
                error="Invalid phone or password"
            )

    cursor.close()
    db.close()

    return render_template('login.html')


# ================= LOGOUT =================
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ================= DASHBOARD =================
@app.route('/')
def home():
    db = get_db()
    if db is None:
        return "Database not connected"

    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) as total FROM farmers")
    farmers = cursor.fetchone()['total'] or 0

    cursor.execute("SELECT IFNULL(SUM(qty),0) as total FROM milk_collection")
    milk = float(cursor.fetchone()['total'] or 0)

    cursor.execute("SELECT IFNULL(SUM(total_amount),0) as total FROM payments")
    payments = float(cursor.fetchone()['total'] or 0)

    cursor.execute("SELECT IFNULL(SUM(total),0) as total FROM sales")
    sales = float(cursor.fetchone()['total'] or 0)

    profit = sales - payments

    cursor.execute("""
        SELECT MONTH(date) as m, IFNULL(SUM(total),0) as total
        FROM sales GROUP BY MONTH(date)
    """)
    sales_data = [0]*6
    for row in cursor.fetchall():
        if row['m'] and 1 <= row['m'] <= 6:
            sales_data[row['m']-1] = float(row['total'])

    cursor.execute("""
        SELECT MONTH(payment_date) as m, IFNULL(SUM(total_amount),0) as total
        FROM payments GROUP BY MONTH(payment_date)
    """)
    payment_data = [0]*6
    for row in cursor.fetchall():
        if row['m'] and 1 <= row['m'] <= 6:
            payment_data[row['m']-1] = float(row['total'])

    profit_data = [sales_data[i] - payment_data[i] for i in range(6)]

    cursor.close()
    db.close()

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
@app.route('/farmers', methods=['GET', 'POST'])
def farmers():

    db = get_db()

    if db is None:
        return "Database not connected"

    cursor = db.cursor(dictionary=True)

    # ================= ADD FARMER =================
    if request.method == 'POST':

        name = request.form['name']
        phone = request.form['phone']

        # GET ALL FARMER CODES
        cursor.execute("SELECT farmer_code FROM farmers")
        codes = cursor.fetchall()

        used = sorted([

            int(c['farmer_code'][1:])

            for c in codes

            if c['farmer_code']
            and c['farmer_code'].startswith('F')

        ])

        # GENERATE NEXT CODE
        new_num = 101

        for num in used:

            if num == new_num:
                new_num += 1
            else:
                break

        farmer_code = f"F{new_num}"

        # INSERT FARMER
        cursor.execute("""

            INSERT INTO farmers
            (farmer_code, name, phone, status)

            VALUES (%s, %s, %s, 'Active')

        """, (farmer_code, name, phone))

        db.commit()

    # ================= SEARCH =================
    search = request.args.get('search', '')

    # ================= PAGINATION =================
    page = request.args.get('page', 1, type=int)

    per_page = 10

    offset = (page - 1) * per_page

    # ================= COUNT TOTAL =================
    if search:

        cursor.execute("""

            SELECT COUNT(*) AS total

            FROM farmers

            WHERE name LIKE %s

        """, ('%' + search + '%',))

    else:

        cursor.execute("""

            SELECT COUNT(*) AS total

            FROM farmers

        """)

    total_farmers = cursor.fetchone()['total']

    import math
    total_pages = math.ceil(total_farmers / per_page)

    # ================= LOAD FARMERS =================
    if search:

        cursor.execute("""

            SELECT *

            FROM farmers

            WHERE name LIKE %s

            ORDER BY f_id DESC

            LIMIT %s OFFSET %s

        """, ('%' + search + '%', per_page, offset))

    else:

        cursor.execute("""

            SELECT *

            FROM farmers

            ORDER BY f_id DESC

            LIMIT %s OFFSET %s

        """, (per_page, offset))

    data = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(

        'farmers.html',

        farmers=data,

        page=page,

        total_pages=total_pages,

        search=search

    )
# ================= MILK =================
@app.route('/milk', methods=['GET','POST'])
def milk():
    db = get_db()
    if db is None:
        return "Database not connected"

    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        farmer_id = request.form['farmer']
        qty = float(request.form['qty'])
        fat = float(request.form['fat'])
        session_type = request.form['session']
        date = request.form['date']
        time = request.form['time']

        rate = 25 + (fat * 7)
        amount = qty * rate

        # INSERT WITHOUT user_phone
        cursor.execute("""
            INSERT INTO milk_collection
            (farmer_id, qty, fat, session, date, time, amount)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (farmer_id, qty, fat, session_type, date, time, amount))

        db.commit()

    # LOAD ALL DATA
    cursor.execute("""
        SELECT m.*, f.name
        FROM milk_collection m
        JOIN farmers f ON m.farmer_id = f.f_id
        ORDER BY m.id DESC
    """)
    data = cursor.fetchall()

    # LOAD ALL FARMERS
    cursor.execute("SELECT * FROM farmers")
    farmers = cursor.fetchall()
    cursor.close()
    db.close()

    return render_template('milk.html', data=data, farmers=farmers)

# ================= PAYMENTS =================
@app.route('/payments', methods=['GET','POST'])
def payments():
    db = get_db()
    if db is None:
        return "Database not connected"

    cursor = db.cursor(dictionary=True)

    # ================= INSERT =================
    if request.method == 'POST':
        farmer_id = request.form['farmer']
        amount = float(request.form['amount'])
        status = request.form['status']

        # INSERT WITHOUT user_phone
        cursor.execute("""
            INSERT INTO payments 
            (farmer_id, total_amount, status, payment_date)
            VALUES (%s,%s,%s,CURDATE())
        """, (farmer_id, amount, status))

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
            ), 0) AS total_milk,

            IFNULL((
                SELECT SUM(p.total_amount)
                FROM payments p
                WHERE p.farmer_id = f.f_id 
                AND p.status='Paid'
            ), 0) AS paid,

            (
                SELECT MAX(p2.payment_date)
                FROM payments p2
                WHERE p2.farmer_id = f.f_id
            ) AS payment_date

        FROM farmers f
    """)

    data = cursor.fetchall()

    # ================= CALCULATE PENDING =================
    for row in data:
        total = float(row['total_milk'] or 0)
        paid = float(row['paid'] or 0)
        pending = total - paid
        row['total_amount'] = round(max(pending, 0), 2)

    # ================= FARMERS DROPDOWN =================
    cursor.execute("SELECT * FROM farmers")
    farmers = cursor.fetchall()
    cursor.close()
    db.close()

    return render_template('payments.html', data=data, farmers=farmers)

# ================= STOCK =================
@app.route('/stock', methods=['GET','POST'])
def stock():
    db = get_db()
    if db is None:
        return "Database not connected"

    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        try:
            product_id = request.form.get('product_id')
            product_name = request.form.get('product_name')
            price = float(request.form.get('price') or 0)
            quantity = float(request.form.get('quantity') or 0)

            cursor.execute("""
                INSERT INTO stock 
                (product_id, product_name, price, quantity, last_updated)
                VALUES (%s,%s,%s,%s,CURDATE())
            """, (product_id, product_name, price, quantity))

            db.commit()

        except Exception as e:
            print("STOCK ERROR:", e)
            return "Error adding stock"

    cursor.execute("""
        SELECT * FROM stock 
        ORDER BY last_updated DESC
    """)
    data = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template('stock.html', data=data)

# ================= SALES =================
@app.route('/sales', methods=['GET','POST'])
def sales():
    db = get_db()
    if db is None:
        return "Database not connected"

    cursor = db.cursor(dictionary=True)

    error = None
    success = None

    if request.method == 'POST':
        try:
            product_id = (request.form.get('product_id') or "").strip()
            quantity = float(request.form.get('quantity') or 0)

            print("FORM:", product_id, quantity)

            if not product_id:
                error = "Please select a product"
            elif quantity <= 0:
                error = "Enter valid quantity"
            else:
                # convert to int to match '01' vs '1'
                pid = int(product_id)

                cursor.execute("""
                    SELECT * FROM stock 
                    WHERE CAST(product_id AS UNSIGNED) = %s
                """, (pid,))
                product = cursor.fetchone()

                print("PRODUCT:", product)

                if not product:
                    error = "Product not found"
                else:
                    stock_qty = float(product['quantity'] or 0)
                    price = float(product['price'] or 0)

                    if quantity > stock_qty:
                        error = f"Only {stock_qty} items available!"
                    else:
                        total = price * quantity

                        cursor.execute("""
                            INSERT INTO sales
                            (product_id, product_name, price, quantity, total, date)
                            VALUES (%s,%s,%s,%s,%s,CURDATE())
                        """, (
                            product['product_id'],   # keeps '01'
                            product['product_name'],
                            price,
                            quantity,
                            total
                        ))

                        cursor.execute("""
                            UPDATE stock 
                            SET quantity=%s 
                            WHERE CAST(product_id AS UNSIGNED) = %s
                        """, (
                            stock_qty - quantity,
                            pid
                        ))

                        db.commit()
                        print("SALE SUCCESS")
                        success = "Sale completed successfully!"

        except Exception as e:
            print("SALES ERROR:", e)
            error = str(e)

    # load sales history
    cursor.execute("""
        SELECT * FROM sales 
        ORDER BY date DESC
    """)
    data = cursor.fetchall()

    # load products for dropdown
    cursor.execute("SELECT * FROM stock")
    products = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        'sales.html',
        data=data,
        products=products,
        error=error,
        success=success
    )
@app.route('/history', methods=['GET', 'POST'])
def history():

    db = get_db()

    if db is None:
        return "Database not connected"

    cursor = db.cursor(dictionary=True)

    from datetime import date
    import math

    # ================= DATE FILTER =================
    selected_date = request.args.get('date')

    if not selected_date:
        selected_date = str(date.today())

    # ================= SEARCH =================
    search = request.args.get('search', '')

    # ================= PAGINATION =================
    page = request.args.get('page', 1, type=int)

    per_page = 10

    offset = (page - 1) * per_page

    # ================= COUNT TOTAL RECORDS =================
    if search:

        cursor.execute("""

            SELECT COUNT(*) AS total

            FROM milk_collection m

            JOIN farmers f
            ON m.farmer_id = f.f_id

            WHERE DATE(m.date)=%s
            AND f.name LIKE %s

        """, (selected_date, '%' + search + '%'))

    else:

        cursor.execute("""

            SELECT COUNT(*) AS total

            FROM milk_collection m

            JOIN farmers f
            ON m.farmer_id = f.f_id

            WHERE DATE(m.date)=%s

        """, (selected_date,))

    total_records = cursor.fetchone()['total']

    total_pages = math.ceil(total_records / per_page)

    # ================= FETCH DATA =================
    if search:

        cursor.execute("""

            SELECT
            m.id,
            f.name,
            m.qty,
            m.fat,
            m.amount,
            m.time

            FROM milk_collection m

            JOIN farmers f
            ON m.farmer_id = f.f_id

            WHERE DATE(m.date)=%s
            AND f.name LIKE %s

            ORDER BY m.time ASC

            LIMIT %s OFFSET %s

        """, (
            selected_date,
            '%' + search + '%',
            per_page,
            offset
        ))

    else:

        cursor.execute("""

            SELECT
            m.id,
            f.name,
            m.qty,
            m.fat,
            m.amount,
            m.time

            FROM milk_collection m

            JOIN farmers f
            ON m.farmer_id = f.f_id

            WHERE DATE(m.date)=%s

            ORDER BY m.time ASC

            LIMIT %s OFFSET %s

        """, (
            selected_date,
            per_page,
            offset
        ))

    data = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(

        'history.html',

        data=data,

        selected_date=selected_date,

        search=search,

        page=page,

        total_pages=total_pages

    )


# ================= PROFIT =================
@app.route('/profit')
def profit():
    db = get_db()
    if db is None:
        return "Database not connected"

    cursor = db.cursor(dictionary=True)

    # ================= TOTAL SALES =================
    cursor.execute("SELECT IFNULL(SUM(total),0) as total FROM sales")
    res = cursor.fetchone()
    sales = float(res['total'] if res and res['total'] else 0)

    # ================= TOTAL PAYMENTS =================
    cursor.execute("SELECT IFNULL(SUM(total_amount),0) as total FROM payments")
    res = cursor.fetchone()
    payments = float(res['total'] if res and res['total'] else 0)

    net_profit = sales - payments

    # ================= MONTHLY SALES =================
    cursor.execute("""
        SELECT MONTH(date) as m, IFNULL(SUM(total),0) as total
        FROM sales
        GROUP BY MONTH(date)
    """)
    sales_data = [0]*6
    for row in cursor.fetchall():
        if row['m'] and 1 <= row['m'] <= 6:
            sales_data[row['m']-1] = float(row['total'])

    # ================= MONTHLY PAYMENTS =================
    cursor.execute("""
        SELECT MONTH(payment_date) as m, IFNULL(SUM(total_amount),0) as total
        FROM payments
        GROUP BY MONTH(payment_date)
    """)
    payment_data = [0]*6
    for row in cursor.fetchall():
        if row['m'] and 1 <= row['m'] <= 6:
            payment_data[row['m']-1] = float(row['total'])

    # ================= PROFIT =================
    profit_data = [sales_data[i] - payment_data[i] for i in range(6)]
    cursor.close()
    db.close()

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

    if request.method == 'POST':
        cursor.execute("""
            UPDATE farmers 
            SET name=%s, phone=%s 
            WHERE f_id=%s
        """, (request.form['name'], request.form['phone'], id))
        db.commit()
        return redirect('/farmers')

    cursor.execute("SELECT * FROM farmers WHERE f_id=%s", (id,))
    farmer = cursor.fetchone()
    cursor.close()
    db.close()


    return render_template('edit_farmer.html', farmer=farmer)


@app.route('/delete/<int:id>')
def delete_farmer(id):
    db = get_db()
    if db is None:
        return "Database not connected"

    cursor = db.cursor()

    cursor.execute("DELETE FROM milk_collection WHERE farmer_id=%s", (id,))
    cursor.execute("DELETE FROM payments WHERE farmer_id=%s", (id,))
    cursor.execute("DELETE FROM farmers WHERE f_id=%s", (id,))

    db.commit()
    cursor.close()
    db.close()
    return redirect('/farmers')




@app.route('/delete_stock/<string:product_id>')
def delete_stock(product_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("DELETE FROM stock WHERE product_id=%s", (product_id,))

    db.commit()
    cursor.close()
    db.close()
    return redirect('/stock')


@app.route('/get_amount/<int:farmer_id>')
def get_amount(farmer_id):
    db = get_db()
    if db is None:
        return {"amount": 0}

    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT IFNULL(SUM(amount),0) as total FROM milk_collection WHERE farmer_id=%s", (farmer_id,))
    total = cursor.fetchone()['total'] or 0

    cursor.execute("SELECT IFNULL(SUM(total_amount),0) as paid FROM payments WHERE farmer_id=%s AND status='Paid'", (farmer_id,))
    paid = cursor.fetchone()['paid'] or 0

    cursor.close()
    db.close()

    return {"amount": round(max(float(total) - float(paid), 0), 2)}


@app.route('/edit_stock/<string:product_id>', methods=['GET','POST'])
def edit_stock(product_id):
    db = get_db()
    if db is None:
        return "Database not connected"
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT * FROM stock 
        WHERE product_id=%s
    """, (product_id,))
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
            WHERE product_id=%s
        """, (product_name, price, quantity, product_id))

        db.commit()
        return redirect('/stock')
    cursor.close()
    db.close()

    return render_template('edit_stock.html', data=data)



# ================= APPROVAL USERS =================
@app.route('/approve_users')
def approve_users():

    # ONLY PROPRIETOR CAN ACCESS
    if session['user'] != '8073478057':
        return "Access Denied"

    db = get_db()

    if db is None:
        return "Database not connected"

    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT * FROM manager
        WHERE status='pending'
    """)

    users = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        'approve_users.html',
        users=users
    )


# ================= APPROVE =================
@app.route('/approve/<int:id>')
def approve(id):

    if session['user'] != '8073478057':
        return "Access Denied"

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        UPDATE manager
        SET status='approved'
        WHERE id=%s
    """, (id,))

    db.commit()

    cursor.close()
    db.close()

    return redirect('/approve_users')


# ================= REJECT =================
@app.route('/reject/<int:id>')
def reject(id):

    if session['user'] != '8073478057':
        return "Access Denied"

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        UPDATE manager
        SET status='rejected'
        WHERE id=%s
    """, (id,))

    db.commit()

    cursor.close()
    db.close()

    return redirect('/approve_users')



if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)