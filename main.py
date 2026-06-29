from flask import Flask, render_template, request, flash, redirect
from flask import Response
import pyodbc
from flask import jsonify
from flask import send_from_directory
import os


app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_FOLDER = r"D:\advocate_website\static\uploads"

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER



if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.secret_key = "evc123"

# SQL SERVER CONNECTION

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost;"
    "DATABASE=adv_thakre_cms;"
    "Trusted_Connection=yes;"
)

conn.autocommit = True


# DASHBOARD

@app.route('/')
@app.route('/dashboard')
def dashboard():

    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM evc_clients
        ORDER BY id DESC
    """)

    clients = cursor.fetchall()

    cursor.execute("""
        SELECT COUNT(*)
        FROM evc_clients
    """)
    total_clients = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM evc_clients
        WHERE status='Pending'
    """)
    pending_clients = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM evc_clients
        WHERE status='Verified'
    """)
    verified_clients = cursor.fetchone()[0]

    page = request.args.get('page', 1, type=int)
    per_page = 10

    cursor.execute("""
    SELECT *
    FROM evc_clients
    ORDER BY id DESC
    OFFSET ? ROWS
    FETCH NEXT ? ROWS ONLY
    """, ((page - 1) * per_page, per_page))

    clients = cursor.fetchall()

    return render_template(
        'admin/dashboard.html',
        clients=clients,
        total_clients=total_clients,
        pending_clients=pending_clients,
        verified_clients=verified_clients
    )



@app.route('/fetch-client', methods=['POST'])
def fetch_client():

    pan_no = request.form['pan_no']

    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            PanNo,
            FullName,
            Mobile
        FROM SPL5.dbo.ClientList
        WHERE PanNo = ?
    """, (pan_no,))

    client = cursor.fetchone()

    if not client:

        flash(
            'PAN Number Not Found',
            'danger'
        )

        return redirect('/add-client')

    return render_template(
        'admin/add_client.html',
        client=client
    )

# ADD CLIENT
@app.route('/add-client', methods=['GET', 'POST'])
def add_client():

    cursor = conn.cursor()

    if request.method == "POST":

        pan_no = request.form["pan_no"]
        client_name = request.form["client_name"]
        mobile_no = request.form["mobile_no"]
        date_of_file = request.form["date_of_file"]
        remarks = request.form.get("remarks", "")

        # Get next available Verification Executive
        cursor.execute("""

        SELECT TOP 1
            u.id,
            u.fullname,
            COUNT(c.id) AS pending_count

        FROM users u

        LEFT JOIN evc_clients c
        ON u.id = c.assigned_to
        AND c.status='Pending'

        WHERE u.status='Active'

        GROUP BY
            u.id,
            u.fullname

        HAVING COUNT(c.id) < 20

        ORDER BY
        
        u.id

        """)

        executive = cursor.fetchone()

        if executive is None:

            flash(
                "No Verification Executive Available.",
                "danger"
            )

            return redirect("/add-client")

        assigned_user = executive.id

        cursor.execute("""

        INSERT INTO evc_clients
        (
            pan_no,
            client_name,
            mobile_no,
            date_of_file,
            assigned_to,
            assigned_date,
            remarks
        )

        VALUES
        (
            ?,
            ?,
            ?,
            ?,
            ?,
            GETDATE(),
            ?
        )

        """,
        (
            pan_no,
            client_name,
            mobile_no,
            date_of_file,
            assigned_user,
            remarks
        ))

        flash(

            f"Client assigned to {executive.fullname} successfully.",

            "success"

        )

        return redirect("/add-client")

    ###########################################################
    # Queue for Preview
    ###########################################################

    cursor.execute("""

    SELECT

        u.id,
        u.fullname,
        COUNT(c.id) AS pending_count

    FROM users u

    LEFT JOIN evc_clients c

    ON u.id = c.assigned_to

    AND c.status='Pending'

    WHERE u.status='Active'

    GROUP BY

        u.id,
        u.fullname

    ORDER BY
    
    u.id

    """)

    users = cursor.fetchall()

    return render_template(

        "admin/add_client.html",

        users=users

    )

@app.route('/assign-clients', methods=['GET', 'POST'])
def assign_clients():

    cursor = conn.cursor()

    if request.method == "POST":

        user_id = int(request.form['user_id'])

        limit = int(request.form['limit'])

        cursor.execute("""
        SELECT TOP (?) id

        FROM evc_clients

        WHERE

        status='Pending'

        AND assigned_to IS NULL

        ORDER BY id
        """, (limit,))

        clients = cursor.fetchall()

        for client in clients:

            cursor.execute("""

            UPDATE evc_clients

            SET

            assigned_to=?,

            assigned_date=GETDATE()

            WHERE id=?

            """,

            (

            user_id,

            client.id

            ))

        flash("Clients Assigned Successfully","success")

        return redirect('/assign-clients')

    cursor.execute("""

    SELECT

    id,

    fullname

    FROM users

    WHERE status='Active'

    ORDER BY fullname

    """)

    users = cursor.fetchall()

    return render_template(

    "admin/assign_clients.html",

    users=users

    )

@app.route('/search-pan', methods=['POST'])
def search_pan():

    data = request.get_json()

    pan_no = data['pan_no'].strip().upper()

    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            FileNo,
            FullName,
            Mobile,
            EfilingPassword
        FROM SPL5.dbo.ClientList
        WHERE UPPER(PanNo) = ?
    """, (pan_no,))

    row = cursor.fetchone()

    if row:
        return jsonify({
            "found": True,
            "file_no": row[0],
            "name": row[1],
            "mobile": row[2],
            "efiling_password": row[3]
        })

    return jsonify({
        "found": False
    })

# PENDING CLIENTS


@app.route('/pending-clients')
def pending_clients():

    page = request.args.get('page', 1, type=int)

    per_page = 20

    cursor = conn.cursor()

    # Total Records
    cursor.execute("""
        SELECT COUNT(*)
        FROM evc_clients
        WHERE status='Pending'
    """)

    total_records = cursor.fetchone()[0]

    total_pages = (total_records + per_page - 1) // per_page

    # Paginated Records
    cursor.execute("""
        SELECT *
        FROM evc_clients
        WHERE status='Pending'
        ORDER BY id DESC
        OFFSET ? ROWS
        FETCH NEXT ? ROWS ONLY
    """,
    (
        (page - 1) * per_page,
        per_page
    ))

    clients = cursor.fetchall()

    return render_template(
        'admin/pending_clients.html',
        clients=clients,
        page=page,
        total_pages=total_pages,
        total_records=total_records
    )



# VERIFIED CLIENTS

@app.route('/verified-clients')
def verified_clients():

    search = request.args.get('search','')

    page = request.args.get('page',1,type=int)

    per_page = 10

    cursor = conn.cursor()

    where_clause = """
    WHERE status='Verified'
    """

    params = []

    if search:

        where_clause += """
        AND (
            pan_no LIKE ?
            OR client_name LIKE ?
            OR mobile_no LIKE ?
        )
        """

        params.extend([
            f"%{search}%",
            f"%{search}%",
            f"%{search}%"
        ])

    cursor.execute(f"""
        SELECT COUNT(*)
        FROM evc_clients
        {where_clause}
    """, params)

    total_verified = cursor.fetchone()[0]

    total_pages = (
        total_verified + per_page - 1
    ) // per_page

    query = f"""
    SELECT *
    FROM evc_clients
    {where_clause}
    ORDER BY verified_at DESC
    OFFSET ? ROWS
    FETCH NEXT ? ROWS ONLY
    """

    params.extend([
        (page-1)*per_page,
        per_page
    ])

    cursor.execute(query, params)

    clients = cursor.fetchall()

    return render_template(
        'admin/verified_clients.html',
        clients=clients,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        total_verified=total_verified,
        search=search
    )

@app.route('/view-pdf/<int:client_id>')
def view_pdf(client_id):

    cursor = conn.cursor()

    cursor.execute("""
        SELECT evc_pdf
        FROM evc_clients
        WHERE id=?
    """, (client_id,))

    row = cursor.fetchone()

    if not row:
        return "Client not found"

    filename = row.evc_pdf

    if not filename:
        return "PDF not uploaded"

    return redirect(
        f"https://advthakre.com/evc-pdf/{filename}"
    )

if __name__ == '__main__':
    app.run(debug=True)