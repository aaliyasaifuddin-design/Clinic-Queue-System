
from flask import Flask, render_template, request, session, redirect, url_for, flash
import os
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "change-this-to-a-long-random-secret"

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "clinic_queue")
    )


@app.route("/")
def home():
    if "doctor_id" in session:
        return redirect(url_for("dashboard"))

    return redirect(url_for("signup"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form["email"].strip().lower()
    password = request.form["password"]

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT * FROM doctors WHERE email = %s",
            (email,)
        )
        doctor = cursor.fetchone()

        if doctor and check_password_hash(
            doctor["password_hash"], password
        ):
            session["doctor_id"] = doctor["doctor_id"]
            session["doctor_name"] = doctor["doctor_name"]

            return redirect(url_for("dashboard"))

        return "Invalid email or password. Please try again.", 401

    finally:
        cursor.close()
        connection.close()



@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html")

    doctor_name = request.form.get("doctor_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not doctor_name or not email or len(password) < 8:
        return "Please enter all details and a password of at least 8 characters.", 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT doctor_id FROM doctors WHERE email = %s",
            (email,)
        )

        if cursor.fetchone():
            return "This email is already registered. Please log in.", 409

        password_hash = generate_password_hash(password)

        cursor.execute(
            """INSERT INTO doctors
               (doctor_name, email, password_hash)
               VALUES (%s, %s, %s)""",
            (doctor_name, email, password_hash)
        )

        connection.commit()
        return redirect(url_for("login"))

    except mysql.connector.Error:
        connection.rollback()
        return "Could not create account. Please try again.", 500

    finally:
        cursor.close()
        connection.close()



@app.route("/patients")
def view_patients():
    if "doctor_id" not in session:
        return redirect(url_for("login"))

    clinic_id = request.args.get("clinic_id", type=int)

    if clinic_id is None:
        return "Please select a clinic.", 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Check that this clinic belongs to the logged-in doctor
        cursor.execute(
            """SELECT clinic_id, clinic_name, city
               FROM clinics
               WHERE clinic_id = %s AND doctor_id = %s""",
            (clinic_id, session["doctor_id"])
        )
        clinic = cursor.fetchone()

        if not clinic:
            return "Clinic not found or access denied.", 403

        cursor.execute(
            """SELECT id, patient_name, patient_age, phone,
                      clinic_id, clinic_patient_no
               FROM patients
               WHERE clinic_id = %s
               ORDER BY clinic_patient_no ASC""",
            (clinic_id,)
        )
        patients = cursor.fetchall()

        return render_template(
            "patients.html",
            patients=patients,
            clinics=[clinic],
            selected_clinic_id=clinic_id
        )

    finally:
        cursor.close()
        connection.close()



@app.route("/register/<int:clinic_id>", methods=["GET", "POST"])
def register(clinic_id):
    if "doctor_id" not in session:
        return redirect(url_for("login"))

    if request.method == "GET":
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        try:
            cursor.execute(
                """SELECT clinic_id, clinic_name
                   FROM clinics
                   WHERE clinic_id = %s AND doctor_id = %s""",
                (clinic_id, session["doctor_id"])
            )
            clinic = cursor.fetchone()

            if not clinic:
                return "Clinic not found or access denied.", 403

            return render_template("index.html", clinic=clinic)

        finally:
            cursor.close()
            connection.close()

    try:
        patient_name = request.form.get("patient_name", "").strip()
        patient_age = int(request.form.get("patient_age", ""))
        phone = request.form.get("phone", "").strip()
    except (ValueError, TypeError):
        return "Please enter valid patient details.", 400

    if not patient_name or not phone or patient_age < 0:
        return "Please enter valid patient details.", 400

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        connection.start_transaction()

        cursor.execute(
            """SELECT clinic_id
               FROM clinics
               WHERE clinic_id = %s AND doctor_id = %s
               FOR UPDATE""",
            (clinic_id, session["doctor_id"])
        )

        if cursor.fetchone() is None:
            connection.rollback()
            return "Clinic not found or access denied.", 403

        cursor.execute(
            """SELECT COALESCE(MAX(clinic_patient_no), 0) + 1
               FROM patients
               WHERE clinic_id = %s""",
            (clinic_id,)
        )
        next_patient_no = cursor.fetchone()[0]

        cursor.execute(
            """INSERT INTO patients
               (patient_name, patient_age, phone, clinic_id, clinic_patient_no)
               VALUES (%s, %s, %s, %s, %s)""",
            (patient_name, patient_age, phone, clinic_id, next_patient_no)
        )

        connection.commit()
        flash("Patient Registered Successfully!", "success")
        return redirect(url_for("view_patients", clinic_id=clinic_id))

    except mysql.connector.Error:
        connection.rollback()
        return "Could not register patient. Please try again.", 500

    finally:
        cursor.close()
        connection.close()
    
@app.route("/register-clinic", methods=["GET", "POST"])
def register_clinic():
    if "doctor_id" not in session:
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("clinic_signup.html")

    clinic_name = request.form.get("clinic_name", "").strip()
    city = request.form.get("city", "").strip()
    address = request.form.get("address", "").strip()

    if not clinic_name or not city or not address:
        return "Please enter all clinic details.", 400

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """INSERT INTO clinics
               (doctor_id, clinic_name, city, address)
               VALUES (%s, %s, %s, %s)""",
            (session["doctor_id"], clinic_name, city, address)
        )

        connection.commit()
        return redirect(url_for("dashboard"))

    except mysql.connector.Error:
        connection.rollback()
        return "Could not register clinic. Please try again.", 500

    finally:
        cursor.close()
        connection.close()


@app.route("/dashboard")
def dashboard():
    if "doctor_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """SELECT clinic_id, clinic_name, city, address
               FROM clinics
               WHERE doctor_id = %s
               ORDER BY clinic_id""",
            (session["doctor_id"],)
        )
        clinics = cursor.fetchall()

        return render_template(
            "clinic_dashboard.html",
            doctor_name=session.get("doctor_name", "Doctor"),
            clinics=clinics
        )

    finally:
        cursor.close()
        connection.close()


@app.route("/display/<int:clinic_id>")
def display(clinic_id):
    if "doctor_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """SELECT clinic_id, clinic_name
               FROM clinics
               WHERE clinic_id = %s AND doctor_id = %s""",
            (clinic_id, session["doctor_id"])
        )
        clinic = cursor.fetchone()

        if not clinic:
            return "Clinic not found or access denied.", 403

        cursor.execute(
            """SELECT clinic_patient_no, patient_name
               FROM patients
               WHERE clinic_id = %s AND status = 'in_cabin'
               ORDER BY clinic_patient_no ASC
               LIMIT 1""",
            (clinic_id,)
        )
        current_patient = cursor.fetchone()

        cursor.execute(
            """SELECT clinic_patient_no, patient_name
               FROM patients
               WHERE clinic_id = %s AND status = 'waiting'
               ORDER BY clinic_patient_no ASC
               LIMIT 1""",
            (clinic_id,)
        )
        next_patient = cursor.fetchone()

        cursor.execute(
            """SELECT COUNT(*) AS waiting_count
               FROM patients
               WHERE clinic_id = %s AND status = 'waiting'""",
            (clinic_id,)
        )
        waiting_count = cursor.fetchone()["waiting_count"]

        waiting_time = 5 if current_patient else 0

        return render_template(
            "display.html",
            clinic=clinic,
            current_patient=current_patient,
            next_patient=next_patient,
            waiting_time=waiting_time,
            waiting_count=waiting_count
        )
    

    finally:
        cursor.close()
        connection.close()

    
     
        
@app.route("/call-next/<int:clinic_id>", methods=["POST"])
def call_next_patient(clinic_id):
    if "doctor_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        connection.start_transaction()

        cursor.execute(
            """SELECT clinic_id
               FROM clinics
               WHERE clinic_id = %s AND doctor_id = %s
               FOR UPDATE""",
            (clinic_id, session["doctor_id"])
        )
        clinic = cursor.fetchone()

        if not clinic:
            connection.rollback()
            return "Clinic not found or access denied.", 403

        cursor.execute(
            """UPDATE patients
               SET status = 'completed'
               WHERE clinic_id = %s AND status = 'in_cabin'""",
            (clinic_id,)
        )

        cursor.execute(
            """SELECT id
               FROM patients
               WHERE clinic_id = %s AND status = 'waiting'
               ORDER BY clinic_patient_no ASC
               LIMIT 1
               FOR UPDATE""",
            (clinic_id,)
        )
        patient = cursor.fetchone()

        if patient:
            cursor.execute(
                """UPDATE patients
                   SET status = 'in_cabin'
                   WHERE id = %s AND clinic_id = %s""",
                (patient["id"], clinic_id)
            )

        connection.commit()
        return redirect(url_for("dashboard"))

    except mysql.connector.Error:
        connection.rollback()
        return "Could not call next patient. Please try again.", 500

    finally:
        cursor.close()
        connection.close()
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))





if __name__ == "__main__":
    app.run(debug=True)

