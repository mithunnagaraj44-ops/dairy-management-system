from flask import Flask, render_template, request, redirect, session

app = Flask(__name__)
app.secret_key = "secret123"


@app.before_request
def check_login():
    if request.endpoint not in ['login', 'register', 'static']:
        if 'user' not in session:
            return redirect('/login')


# ================= REGISTER =================
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        return redirect('/login')
    return render_template('register.html')


# ================= LOGIN =================
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        phone = request.form['phone']
        password = request.form['password']

        if phone == "123" and password == "123":
            session['user'] = phone
            return redirect('/')
        else:
            return "Invalid login"

    return render_template('login.html')


# ================= LOGOUT =================
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ================= DASHBOARD =================
@app.route('/')
def home():
    return render_template(
        'index.html',
        farmers=6,
        milk=96,
        payments=5186,
        sales=14100,
        profit=8913,
        sales_data=[2000, 2500, 3000, 1500, 2800, 2300],
        profit_data=[1000, 1200, 1500, 800, 1300, 1100]
    )


# ================= FARMERS =================
@app.route('/farmers', methods=['GET','POST'])
def farmers():
    data = [
        {"f_id":1, "farmer_code":"F101", "name":"Kishor", "phone":"9999"},
        {"f_id":2, "farmer_code":"F102", "name":"Sinchana", "phone":"8888"},
        {"f_id":3, "farmer_code":"F103", "name":"Mithun", "phone":"7777"},
    ]
    return render_template('farmers.html', farmers=data)


# ================= MILK =================
@app.route('/milk')
def milk():
    return render_template('milk.html', data=[], farmers=[])


# ================= PAYMENTS =================
@app.route('/payments')
def payments():
    data = [
        {"f_id":1, "farmer_code":"F101", "name":"Kishor", "total_amount":120, "payment_date":"2026-04-01"},
        {"f_id":2, "farmer_code":"F102", "name":"Sinchana", "total_amount":52.6, "payment_date":"-"},
        {"f_id":3, "farmer_code":"F103", "name":"Mithun", "total_amount":38.4, "payment_date":"-"},
    ]
    return render_template('payments.html', data=data, farmers=data)


# ================= STOCK =================
@app.route('/stock')
def stock():
    data = [
        {"id":1, "product_name":"Milk 1L", "price":50, "quantity":20},
        {"id":2, "product_name":"Curd", "price":30, "quantity":15},
    ]
    return render_template('stock.html', data=data)


# ================= SALES =================
@app.route('/sales')
def sales():
    return render_template('sales.html', data=[], products=[])


# ================= HISTORY =================
@app.route('/history')
def history():
    return render_template('history.html', data=[], selected_date="2026-04-18")


# ================= PROFIT =================
@app.route('/profit')
def profit():
    return render_template(
        'profit.html',
        sales=14100,
        payments=5186,
        net_profit=8913,
        sales_data=[2000,2500,3000,1500,2800,2300],
        profit_data=[1000,1200,1500,800,1300,1100]
    )


if __name__ == '__main__':
    app.run(debug=True)