from flask import jsonify, request
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask import jsonify
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file, make_response
# import mysql.connector
import traceback
import pymysql
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, timezone
import logging
import io
import math
from io import BytesIO
import json
import xlsxwriter

import pandas as pd
from ou1 import store_results_in_db, scrape_ou_results, determine_semester, get_result_page
import requests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
app = Flask(__name__)
app.secret_key = 'Admin'  # Set a secret key for session management

# Set the session lifetime to 20 minutes
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=20)


# Enable secure cookies (for HTTPS only) - Disabled for development
# app.config['SESSION_COOKIE_SECURE'] = True

# Set up logging
app.logger.setLevel(logging.INFO)


@app.before_request
def make_session_permanent():
    if 'identifier' in session:
        session.permanent = True


# Database connection
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'ammu2007',  # Update with your actual password
    'database': 'user_management'
}


def get_db_connection():
    try:
        connection = pymysql.connect(
            host='localhost',
            user='root',
            password='ammu2007',
            database='user_management',
            cursorclass=pymysql.cursors.DictCursor
        )
        return connection
    except pymysql.MySQLError as err:
        print(f"Database connection failed: {err}")
        return None


# Helper function to check and create individual tables if missing

def check_and_create_table(connection, table_name, creation_query):
    with connection.cursor() as cursor:
        cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
        result = cursor.fetchone()
        if not result:
            cursor.execute(creation_query)
            logging.info(f"Table '{table_name}' created successfully.")
        else:
            logging.info(f"Table '{table_name}' already exists.")


# Function to initialize database and tables


def create_tables():
    connection = pymysql.connect(
        host='localhost',
        user='root',
        password='ammu2007'
    )
    cursor = connection.cursor()
    # Create the database if it doesn't exist
    cursor.execute("CREATE DATABASE IF NOT EXISTS user_management")
    connection.commit()
    cursor.close()
    connection.close()

    # Reconnect to the newly created database
    connection = pymysql.connect(
        host='localhost',
        user='root',
        password='ammu2007',
        database='user_management'
    )

    table_creation_data = {
        'users': """
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(255) NOT NULL UNIQUE,
                password TEXT NOT NULL,
                role VARCHAR(50) NOT NULL,
                original_password VARCHAR(255) NOT NULL
            )
        """,
        'faculty_user': """
            CREATE TABLE IF NOT EXISTS faculty_user (
    faculty_id INT PRIMARY KEY,                          -- Unique faculty ID (manually assigned)
    first_name VARCHAR(50) NOT NULL,                    -- First name
    last_name VARCHAR(50) NOT NULL,                     -- Last name
    email VARCHAR(100) UNIQUE NOT NULL,                 -- Email address
    phone_number VARCHAR(15),                           -- Contact number
    department_id INT NOT NULL,                         -- Reference to the department
    designation VARCHAR(50),                            -- Designation
    joining_date DATE,                                  -- Date of joining
    salary DECIMAL(10,2),                               -- Salary
    password TEXT NOT NULL,                             -- Password (hashed)
    roles JSON NOT NULL,                                -- Roles in JSON format
    status ENUM('active', 'inactive') DEFAULT 'active', -- Status
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,     -- Creation timestamp
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP                     -- Last update timestamp
);

         """,
        'assigned_elective_access': """

    CREATE TABLE assigned_elective_access (
     id INT AUTO_INCREMENT PRIMARY KEY,
     year VARCHAR(255) NOT NULL,
     branch VARCHAR(255) NOT NULL,
     semester ENUM('1','2','3','4','5','6','7','8') NOT NULL,
     subjects JSON NOT NULL,
     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
     updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
     );
""",
        'student_electives': """
        CREATE TABLE student_electives (
    id INT AUTO_INCREMENT PRIMARY KEY,
    roll_number VARCHAR(50) NOT NULL,
    subject_code VARCHAR(50) NOT NULL,
    FOREIGN KEY (subject_code) REFERENCES subject(subject_code) ON DELETE CASCADE,
    UNIQUE KEY unique_student_elective (roll_number, subject_code)
);
        """,


        'Department': """
        CREATE TABLE Department (
    department_id INT PRIMARY KEY,     -- Department ID (fixed 3 characters)
    department_name VARCHAR(255) NOT NULL, -- Department name with max length of 255 characters
    department_head INT,                   -- Reference to faculty_id of the head of the department
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- Record creation timestamp
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP -- Last update timestamp
);

        """,
        'InternalMarksAccess': """
            CREATE TABLE IF NOT EXISTS InternalMarksAccess (
                id INT AUTO_INCREMENT PRIMARY KEY,
                component_name VARCHAR(50) NOT NULL UNIQUE,
                access_status ENUM('ON', 'OFF') DEFAULT 'OFF',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            );
        """,
        'Subject': """
            CREATE TABLE subject (
  subject_id INT AUTO_INCREMENT PRIMARY KEY,         -- Unique course ID
  subject_name VARCHAR(100) NOT NULL,                -- Course name
  subject_code VARCHAR(20) NOT NULL UNIQUE,          -- Unique course code (e.g., CS101)
  department_id INT NOT NULL,                        -- Reference to the department offering the course
  semester ENUM('1', '2', '3', '4', '5', '6', '7', '8'), -- Semester in which the course is taught
  credits INT NOT NULL,                              -- Number of credits for the course
  elective ENUM('Core', 'Professional Elective', 'Open Elective') NOT NULL DEFAULT 'Core',  -- Elective Type
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,    -- Record creation timestamp
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, -- Last update timestamp
  FOREIGN KEY (department_id) REFERENCES department(department_id) -- Foreign key to department
);

        """,
        'faculty_assessment': """
            CREATE TABLE IF NOT EXISTS faculty_assessment (
    faculty_id INT PRIMARY KEY,
    assessment_data JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
        """,

        'internal_marks': """
                CREATE TABLE IF NOT EXISTS internal_marks (
            roll_number VARCHAR(12) NOT NULL,
            subject_code VARCHAR(10) NOT NULL,
            subject_name VARCHAR(255) NOT NULL,
            cie1 INT DEFAULT 0,
            cie2 INT DEFAULT 0,
            total INT DEFAULT 0,
            assignment INT DEFAULT 0,
            avg INT DEFAULT 0,
            passed_out_year INT NOT NULL,
            semester INT NOT NULL,
            PRIMARY KEY (roll_number, subject_code, passed_out_year, semester),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """,
        'notifications': """
            CREATE TABLE IF NOT EXISTS notifications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                message TEXT NOT NULL,
                posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                admin_username VARCHAR(255)
            )
        """,


        'sem1': """
            CREATE TABLE IF NOT EXISTS sem1 (
                id INT AUTO_INCREMENT PRIMARY KEY,
                passed_out_year INT,
                roll_number VARCHAR(255),
                subject_code VARCHAR(255),
                subject_name VARCHAR(255),
                credits FLOAT,
                grade_secured VARCHAR(255),
                grade_point INT,
                exam_series VARCHAR(20) DEFAULT 'Regular'
            )
        """,
        'sem2': """
            CREATE TABLE IF NOT EXISTS sem2 (
                id INT AUTO_INCREMENT PRIMARY KEY,
                passed_out_year INT,
                roll_number VARCHAR(255),
                subject_code VARCHAR(255),
                subject_name VARCHAR(255),
                credits FLOAT,
                grade_secured VARCHAR(255),
                grade_point INT,
                exam_series VARCHAR(20) DEFAULT 'Regular'
            )
        """,
        'sem3': """
            CREATE TABLE IF NOT EXISTS sem3 (
                id INT AUTO_INCREMENT PRIMARY KEY,
                passed_out_year INT,
                roll_number VARCHAR(255),
                subject_code VARCHAR(255),
                subject_name VARCHAR(255),
                credits FLOAT,
                grade_secured VARCHAR(255),
                grade_point INT,
                exam_series VARCHAR(20) DEFAULT 'Regular'
            )
        """,
        'sem4': """
            CREATE TABLE IF NOT EXISTS sem4 (
                id INT AUTO_INCREMENT PRIMARY KEY,
                passed_out_year INT,
                roll_number VARCHAR(255),
                subject_code VARCHAR(255),
                subject_name VARCHAR(255),
                credits FLOAT,
                grade_secured VARCHAR(255),
                grade_point INT,
                exam_series VARCHAR(20) DEFAULT 'Regular'
            )
        """,
        'sem5': """
            CREATE TABLE IF NOT EXISTS sem5 (
                id INT AUTO_INCREMENT PRIMARY KEY,
                passed_out_year INT,
                roll_number VARCHAR(255),
                subject_code VARCHAR(255),
                subject_name VARCHAR(255),
                credits FLOAT,
                grade_secured VARCHAR(255),
                grade_point INT,
                exam_series VARCHAR(20) DEFAULT 'Regular'
            )
        """,
        'sem6': """
            CREATE TABLE IF NOT EXISTS sem6 (
                id INT AUTO_INCREMENT PRIMARY KEY,
                passed_out_year INT,
                roll_number VARCHAR(255),
                subject_code VARCHAR(255),
                subject_name VARCHAR(255),
                credits FLOAT,
                grade_secured VARCHAR(255),
                grade_point INT,
                exam_series VARCHAR(20) DEFAULT 'Regular'
            )
        """,
        'sem7': """
            CREATE TABLE IF NOT EXISTS sem7 (
                id INT AUTO_INCREMENT PRIMARY KEY,
                passed_out_year INT,
                roll_number VARCHAR(255),
                subject_code VARCHAR(255),
                subject_name VARCHAR(255),
                credits FLOAT,
                grade_secured VARCHAR(255),
                grade_point INT,
                exam_series VARCHAR(20) DEFAULT 'Regular'
            )
        """,
        'sem8': """
            CREATE TABLE IF NOT EXISTS sem8 (
                id INT AUTO_INCREMENT PRIMARY KEY,
                passed_out_year INT,
                roll_number VARCHAR(255),
                subject_code VARCHAR(255),
                subject_name VARCHAR(255),
                credits FLOAT,
                grade_secured VARCHAR(255),
                grade_point INT,
                exam_series VARCHAR(20) DEFAULT 'Regular'
            )
        """
    }

    try:
        # Check and create each table if it does not exist
        for table_name, creation_query in table_creation_data.items():
            check_and_create_table(connection, table_name, creation_query)

        # Create the admin user if it doesn't exist
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM users WHERE username = %s", ('super_admin',))
            admin_user = cursor.fetchone()
            if not admin_user:
                hashed_password = generate_password_hash(
                    'glwec@admin', method='scrypt')
                cursor.execute(
                    "INSERT INTO users (username, password, role, original_password) VALUES (%s, %s, %s, %s)",
                    ('super_admin', hashed_password, 'super_admin', 'glwec@admin')

                )
                logging.info("Admin user created successfully.")
            else:
                logging.info("Admin user already exists.")
             # 2. Check if the default department exists and insert if not
            cursor.execute(
                "SELECT * FROM Department WHERE department_id = %s", (0,))
            department = cursor.fetchone()
            if not department:
                cursor.execute(
                    "INSERT INTO Department (department_id, department_name) VALUES (%s, %s)",
                    (0, 'Non Teaching')
                )
                logging.info(
                    "Default department 'non_teaching' inserted successfully.")
            else:
                logging.info(
                    "Default department 'non_teaching' already exists.")

            connection.commit()

        logging.info("Tables checked and created as needed.")
    except Exception as e:
        logging.error(f"Error creating tables: {str(e)}")
    finally:
        connection.close()


# Call the function to create the database and tables if they don't exist
create_tables()

@app.route('/')
def index():
    return render_template('login.html')


@app.route('/signin', methods=['POST'])
def signin():
    identifier = request.form.get('username')
    password = request.form.get('password')

    conn = get_db_connection()
    cursor = conn.cursor()

    user = None
    roles = []

    # Fetch user details from `users` table
    cursor.execute("SELECT * FROM users WHERE username = %s", (identifier,))
    user = cursor.fetchone()

    if user:
        roles.append(user['role'].lower())  # Add the primary role for `users`
    else:
        # If not in `users`, check `faculty_user` table
        cursor.execute(
            "SELECT * FROM faculty_user WHERE faculty_id = %s", (identifier,))
        user = cursor.fetchone()
        if user:
            roles += json.loads(user['roles'])  # Add roles for `faculty_user`
            session['faculty_name'] = f"{user['first_name']} {user['last_name']}"

            # Check if faculty, hod, or e-admin is inactive
            if any(role in ['faculty', 'e-admin', 'hod'] for role in roles) and user.get('status', '').lower() == 'inactive':
                cursor.close()
                conn.close()
                return render_template('login.html', error='Your account is inactive. Please contact the admin.')

    cursor.close()
    conn.close()

    if user and check_password_hash(user['password'], password):
        session['username'] = identifier
        session['roles'] = roles
        session['role'] = roles[0] if roles else 'unknown'  # Primary role
        session.permanent = True

        app.logger.info(f"User '{identifier}' logged in with roles {roles}")
        app.logger.info(f"Session data: {session}")

        # Redirect based on role
        if 'super_admin' in roles:
            return redirect(url_for('admin'))
        elif 'faculty' in roles or 'e-admin' in roles or 'hod' in roles:
            return redirect(url_for('home'))  # Redirect to faculty page
        elif 'student' in roles:
            return redirect(url_for('profile'))  # Redirect to student profile
        else:
            app.logger.warning(f"Unknown role for user '{identifier}'")
            return render_template('login.html', error='Your role is not recognized.')

    return render_template('login.html', error='Invalid identifier or password')


@app.route('/admin/notifications', methods=['GET', 'POST'])
def manage_notifications():
    if 'username' not in session:
        flash('You must be logged in to access this page', 'danger')
        return redirect(url_for('login'))

    username = session.get('username')
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if the user is a super_admin in the `users` table
    cursor.execute("SELECT role FROM users WHERE username = %s", (username,))
    user_role = cursor.fetchone()

    if user_role and user_role['role'] == 'super_admin':
        # User is a super_admin, allow access to post notifications
        pass
    else:
        # Check if the user is in the `faculty_users` table with an appropriate role
        cursor.execute(
            "SELECT roles FROM faculty_user WHERE faculty_id = %s", (username,))
        faculty_user = cursor.fetchone()

        if faculty_user:
            # Parse the JSON column and check if the role exists
            roles = json.loads(faculty_user['roles'])
            if any(role in ['hod', 'e-admin', 'admin'] for role in roles):
                # User has the required role (hod, e-admin, or admin), allow posting
                pass
            else:
                flash('You do not have permission to post notifications', 'danger')
                return redirect(url_for('view_notifications'))
        else:
            flash('User not found in faculty users table', 'danger')
            return redirect(url_for('view_notifications'))

    cursor.close()
    conn.close()

    if request.method == 'POST':
        title = request.form['title']
        message = request.form['message']
        admin_username = session.get('username')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO notifications (title, message, admin_username) VALUES (%s, %s, %s)",
            (title, message, admin_username)
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash('Notification posted successfully', 'success')
        return redirect(url_for('manage_notifications'))

    # Fetch notifications here
    notifications = fetch_notifications()

    return render_template('admin_notifications.html', notifications=notifications)


@app.route('/student/notifications', methods=['GET'])
def view_notifications():
    # Check if the user is logged in and not restricted to only specific roles
    if 'username' not in session or session.get('role') in ['super_admin', 'admin', 'e-admin', 'hod']:
        flash(
            'You do not have permission to view notifications as a regular user', 'danger')
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch all notifications
    cursor.execute("SELECT * FROM notifications ORDER BY posted_at DESC")
    notifications = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('student_notifications.html', notifications=notifications)


def fetch_notifications():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Query to fetch all notifications
    cursor.execute(
        "SELECT id, title, message, admin_username, posted_at FROM notifications ORDER BY posted_at DESC"
    )
    result = cursor.fetchall()

    # Debug: Check fetched notifications
    print("Fetched notifications:", result)

    # Close the cursor and connection
    cursor.close()
    conn.close()

    return result  # Return the fetched result directly


@app.route('/admin/notifications/delete/<int:id>', methods=['POST'])
def delete_notification(id):
    # Ensure the user is logged in and has an 'admin' role
    if 'username' not in session:
        flash('You must be logged in to access this page', 'danger')
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get the notification details
    cursor.execute(
        "SELECT admin_username FROM notifications WHERE id = %s", (id,))
    notification = cursor.fetchone()

    if not notification:
        flash('Notification not found', 'danger')
        return redirect(url_for('manage_notifications'))

    # Check if the current user is allowed to delete the notification
    current_user = session.get('username')
    if current_user == notification['admin_username'] or session.get('role') == 'super_admin':
        # User is the author of the notification or is a super admin
        cursor.execute("DELETE FROM notifications WHERE id = %s", (id,))
        conn.commit()
        flash('Notification deleted successfully', 'success')
    else:
        flash('You do not have permission to delete this notification', 'danger')

    cursor.close()
    conn.close()

    return redirect(url_for('manage_notifications'))


@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if 'username' not in session:
        return redirect(url_for('index'))  # Redirect to login if not logged in

    username = session['username']

    if request.method == 'POST':
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        conn = get_db_connection()
        cursor = conn.cursor()

        # Fetch the current password hash from the database
        cursor.execute(
            "SELECT password FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()

        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('change_password'))

        # Check if the old password matches the one in the database
        if not check_password_hash(user['password'], old_password):
            flash('Old password is incorrect.', 'error')
            return redirect(url_for('change_password'))

        # Check if the new password is the same as the old password
        if old_password == new_password:
            flash('New password cannot be the same as the old password.', 'error')
            return redirect(url_for('change_password'))

        # Check if the new password meets the minimum length requirement
        if len(new_password) < 6:
            flash('New password must be at least 6 characters long.', 'error')
            return redirect(url_for('change_password'))

        # Check if the new password and confirm password match
        if new_password != confirm_password:
            flash('New password and confirmation do not match.', 'error')
            return redirect(url_for('change_password'))

        # Hash the new password and update both 'password' and 'original_password' in the database
        new_password_hash = generate_password_hash(new_password)

        cursor.execute("""
            UPDATE users
            SET password = %s, original_password = %s
            WHERE username = %s
        """, (new_password_hash, new_password, username))  # Store new password hash and original password

        conn.commit()

        cursor.close()
        conn.close()

        flash('Password changed successfully.', 'success')
        return redirect(url_for('profile'))

    return render_template('change_password.html')


def fetch_results(roll_number, sem):
    db = get_db_connection()
    cursor = db.cursor()
    query = f"""
    SELECT exam_series,subject_code, subject_name, grade_secured, grade_point, credits
    FROM {sem}
    WHERE roll_number = %s
    """
    cursor.execute(query, (roll_number,))
    results = cursor.fetchall()
    cursor.close()
    db.close()
    return results


def fetch_sgpa(roll_number):
    db = get_db_connection()
    cursor = db.cursor()

    query = """
    SELECT sem1_sgpa, sem2_sgpa, sem3_sgpa, sem4_sgpa, 
           sem5_sgpa, sem6_sgpa, sem7_sgpa, sem8_sgpa, 
           sem1_actual_sgpa, sem2_actual_sgpa, sem3_actual_sgpa, sem4_actual_sgpa, 
           sem5_actual_sgpa, sem6_actual_sgpa, sem7_actual_sgpa, sem8_actual_sgpa, 
           no_of_backlogs, cgpa, Status
    FROM sgpa_cgpa WHERE roll_number = %s LIMIT 1
    """

    cursor.execute(query, (roll_number,))
    sgpa_data = cursor.fetchone()
    cursor.close()
    db.close()

    if sgpa_data is not None:
        # Determine which SGPA to show for each semester
        final_sgpa = {}
        for i in range(1, 9):
            sem_sgpa_key = f"sem{i}_sgpa"
            sem_actual_sgpa_key = f"sem{i}_actual_sgpa"

            # If student has any backlogs in that semester, use calculated SGPA
            if sgpa_data["no_of_backlogs"] and int(sgpa_data["no_of_backlogs"]) > 0:
                final_sgpa[f"sem{i}"] = sgpa_data[sem_sgpa_key]
            else:  # Otherwise, use actual SGPA
                final_sgpa[f"sem{i}"] = sgpa_data[sem_actual_sgpa_key]

        sgpa_data["final_sgpa"] = final_sgpa  # Store final SGPA results

        return sgpa_data
    return None


@app.route('/academic_result')
def academic_result():
    roll_number = session.get('username')
    if not roll_number:
        return redirect(url_for('index'))

    all_sem_results = {}
    sgpa_data = fetch_sgpa(roll_number)
    internal_marks_data = {}

    for sem in range(1, 9):
        sem_name = f"sem{sem}"
        all_sem_results[sem_name] = fetch_results(roll_number, sem_name)

        # Fetch internal marks for the current semester
        internal_marks = fetch_internal_marks(roll_number, sem)
        if internal_marks:
            internal_marks_data[sem_name] = internal_marks

    db = get_db_connection()
    cursor = db.cursor()

    query = """
        SELECT Branch, roll_number, `Admitted year`, `Passed out year`, `STUDENT NAME`, 
               `FATHER NAME`, `DATE OF BIRTH (MM/DD/YYYY)`, Sex, `Joined By`, 
               `Rank`, `SSC Marks`, `Inter/ Diploma Marks`
        FROM profile WHERE roll_number = %s
    """
    cursor.execute(query, (roll_number,))
    student = cursor.fetchone()

    # Fetch CGPA and No. of Backlogs from sgpa_cgpa table
    cgpa_query = """
        SELECT cgpa, no_of_backlogs FROM sgpa_cgpa WHERE roll_number = %s
    """
    cursor.execute(cgpa_query, (roll_number,))
    cgpa_result = cursor.fetchone()

    cursor.close()
    db.close()

    cgpa = cgpa_result['cgpa'] if cgpa_result else None
    no_of_backlogs = cgpa_result['no_of_backlogs'] if cgpa_result else None
    flattened_internal_marks_data = {
        k: v for k, v in internal_marks_data.items() if v}

    if student:
        return render_template('academic_result.html',
                               all_sem_results=all_sem_results,
                               sgpa_data=sgpa_data,  # Updated SGPA logic
                               internal_marks_data=flattened_internal_marks_data,
                               student=student,
                               roll_number=roll_number,
                               cgpa=cgpa,
                               no_of_backlogs=no_of_backlogs)
    return render_template('academic_result.html', error="No student found.")


def fetch_internal_marks(roll_number, semester):
    """Fetch internal marks for a given roll number and semester."""
    db = get_db_connection()
    cursor = db.cursor()

    query = """
        SELECT subject_name, cie1, cie2, total, assignment, avg
        FROM internal_marks
        WHERE roll_number = %s AND semester = %s
    """
    cursor.execute(query, (roll_number, semester))
    internal_marks = cursor.fetchall()

    cursor.close()
    db.close()
    return internal_marks


'''@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    roll_number = session.get('username')
    if not roll_number:
        return redirect(url_for('index'))

    db = get_db_connection()
    cursor = db.cursor()

    if request.method == 'POST':
        updated_data = request.form.to_dict()  # Get all form data as a dictionary

        # Ensure username is included in updated_data
        if 'roll_number' not in updated_data:
            updated_data['roll_number'] = roll_number

        # Build the dynamic update query
        set_clause = ", ".join(
            [f"`{col}` = %s" for col in updated_data.keys() if col != 'roll_number'])
        values = [value for key, value in updated_data.items() if key !=
                  'roll_number'] + [roll_number]

        update_query = f"UPDATE profile SET {set_clause} WHERE roll_number = %s"

        try:
            cursor.execute(update_query, values)
            db.commit()

            if cursor.rowcount == 0:
                flash("No changes were made to the profile.")
            else:
                flash("Profile updated successfully!")
                return redirect(url_for('profile'))

        except Exception as e:
            db.rollback()
            flash(f"An error occurred while updating the profile: {str(e)}")

    query = "SELECT * FROM profile WHERE roll_number = %s"
    cursor.execute(query, (roll_number,))
    profile_details = cursor.fetchone()

    cursor.close()
    db.close()

    return render_template('edit_profile.html', profile_details=profile_details)
'''


@app.route('/profile')
def profile():
    roll_number = session.get('username')
    if not roll_number:
        return redirect(url_for('index'))  # Redirect if no roll number

    db = get_db_connection()
    cursor = db.cursor()

    # Query to get profile data
    query = "SELECT * FROM profile WHERE roll_number = %s"
    cursor.execute(query, (roll_number,))
    profile_details = cursor.fetchone()  # Fetch profile details for the roll number

    # Close the database connection
    cursor.close()
    db.close()

    return render_template('student_page.html', profile_details=profile_details)


# Teacher page route


@app.route('/home')
def home():
    # Check if the user is logged in
    if 'username' not in session or 'roles' not in session:
        return redirect(url_for('signin'))

    identifier = session['username']  # Use the correct key
    roles = session['roles']

    # Connect to the database
    conn = get_db_connection()
    cursor = conn.cursor()

    faculty = None

    try:
        # Fetch faculty details only if the user has faculty-related roles
        if any(role in ['faculty', 'hod', 'e-admin'] for role in roles):
            cursor.execute(
                "SELECT * FROM faculty_user WHERE faculty_id = %s", (identifier,))
            faculty = cursor.fetchone()

        # If not a faculty member or no faculty data found
        if not faculty:
            return render_template('faculty.html', error="Faculty information not found")

        # Pass the details to the template
        return render_template('faculty.html', faculty=faculty)

    except Exception as e:
        app.logger.error(f"Error in /home: {e}")
        return render_template('faculty.html', error="An error occurred while fetching faculty information.")
    finally:
        cursor.close()
        conn.close()


@app.route('/teacher')
def teacher():
    if 'roles' not in session:
        return redirect(url_for('signin'))
    return render_template('teacher.html')


@app.route('/hod')
def hod():
    if 'roles' not in session:
        return redirect(url_for('signin'))
    return render_template('hod.html')
# Logout route

# faculty assignment

# doubt


@app.route('/get_faculty_hod', methods=['GET'])
def get_faculty():
    connection = pymysql.connect(**db_config)
    cursor = connection.cursor()
    cursor.execute(
        "SELECT faculty_id, first_name, last_name FROM faculty_user")
    faculty_data = cursor.fetchall()
    cursor.close()
    connection.close()
    return jsonify(faculty_data)

# doubt


@app.route('/get_subjects_hod', methods=['GET'])
def get_subjects():
    connection = pymysql.connect(**db_config)
    cursor = connection.cursor()
    cursor.execute("SELECT subject_code, subject_name FROM subject")
    subjects = cursor.fetchall()
    cursor.close()
    connection.close()
    return jsonify(subjects)

# doubt


# downalod mid marks super_admin


@app.route('/get_branch_sections_hod', methods=['GET'])
def get_branch_sections():
    connection = pymysql.connect(**db_config)
    cursor = connection.cursor(
        pymysql.cursors.DictCursor)  # Fetch as dictionary
    cursor.execute("SELECT branch, sections FROM branch_sections")
    branch_sections = cursor.fetchall()
    cursor.close()
    connection.close()
    return jsonify(branch_sections)


# doubt


@app.route('/submit_assessment_hod', methods=['POST'])
def submit_assessment():
    active_tab = request.args.get('active_tab', 'faculty_access')
    try:
        data = request.json  # Expecting JSON data
        print("Received Data:", data)

        # Validate the structure of the incoming data
        if 'faculty_id' not in data or 'assessments' not in data:
            error_message = "Missing required keys (faculty_id or assessments)"
            return jsonify({'error': error_message})

        faculty_id = data['faculty_id']

        # Check if the selected faculty has the "faculty" role
        connection = pymysql.connect(**db_config)
        cursor = connection.cursor()
        query_role_check = "SELECT roles FROM faculty_user WHERE faculty_id = %s"
        cursor.execute(query_role_check, (faculty_id,))
        result = cursor.fetchone()
        if not result:
            error_message = "Invalid faculty_id"
            return jsonify({'error': error_message})

        roles = result[0]
        # Ensure roles is properly parsed from JSON
        if "faculty" not in json.loads(roles):
            error_message = "Selected user does not have the faculty role"
            return jsonify({'error': error_message})

        assessments = data['assessments']

        # Ensure assessments is a list
        if not isinstance(assessments, list):
            error_message = "Assessments must be a list"
            return jsonify({'error': error_message})

        # Build the overall JSON structure for storing in the database
        assessment_data = {}
        for assessment in assessments:
            required_keys = ['subject_code', 'active_year', 'branch_section']
            if not all(key in assessment for key in required_keys):
                error_message = f"Missing required keys in assessment: {assessment}"
                return jsonify({'error': error_message})

            subject_code = str(assessment['subject_code'])
            active_year = str(assessment['active_year'])
            branch_sections = assessment['branch_section']

            if subject_code not in assessment_data:
                assessment_data[subject_code] = {}
            assessment_data[subject_code][active_year] = branch_sections

        # Serialize the data
        serialized_data = json.dumps(assessment_data)

        # Check if faculty_id exists in faculty_assessment
        query_check = "SELECT COUNT(*) FROM faculty_assessment WHERE faculty_id = %s"
        cursor.execute(query_check, (faculty_id,))
        exists = cursor.fetchone()[0] > 0

        if exists:
            # Update the existing record
            query_update = """
            UPDATE faculty_assessment
            SET assessment_data = %s
            WHERE faculty_id = %s
            """
            cursor.execute(query_update, (serialized_data, faculty_id))
        else:
            # Insert a new record
            query_insert = """
            INSERT INTO faculty_assessment (faculty_id, assessment_data)
            VALUES (%s, %s)
            """
            cursor.execute(query_insert, (faculty_id, serialized_data))

        connection.commit()
        success_message = "Data successfully saved!"
        return jsonify({'success': success_message})

    except pymysql.MySQLError as e:
        print(f"Database Error: {e}")
        error_message = "Failed to save data"
        return jsonify({'error': error_message})
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

# faculty assignment doubt


@app.route('/get_faculties', methods=['GET'])
def get_faculties():
    """Fetch faculty data to populate the dropdown."""
    try:
        connection = pymysql.connect(**db_config)
        cursor = connection.cursor()
        query = "SELECT faculty_id, first_name, last_name, roles FROM faculty_user"
        cursor.execute(query)
        faculties = cursor.fetchall()

        faculty_list = []
        for faculty_id, first_name, last_name, roles in faculties:
            is_faculty = "faculty" in json.loads(roles)
            faculty_list.append({
                "id": faculty_id,
                "name": f"{first_name} {last_name}",
                "is_faculty": is_faculty
            })

    except pymysql.MySQLError as e:
        print(f"Database Error: {e}")
        return jsonify({"error": "Failed to fetch faculties"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

    return jsonify(faculty_list)

# download excel template


@app.route('/download_excel_with_columns', methods=['GET'])
def download_excel_with_columns():
    try:
        # Fetch column headers from the "profile" table
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SHOW COLUMNS FROM profile")
        columns = [column[0] for column in cursor.fetchall()]
        cursor.close()
        connection.close()

        # Create an empty DataFrame with these columns
        df = pd.DataFrame(columns=columns)

        # Convert DataFrame to Excel file
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Profile Data')

        # Prepare file for download
        output.seek(0)
        return send_file(
            output,
            as_attachment=True,
            download_name='profile_template.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

# internal marks enter faculty page


@app.route('/get_subjects_and_sections', methods=['GET'])
def get_subjects_and_sections():
    try:
        # Assuming session is set up and contains 'username' for the faculty ID
        faculty_id = session.get('username')

        if not faculty_id:
            return jsonify({'error': 'Faculty ID not found in session'}), 401

        connection = pymysql.connect(**db_config)
        cursor = connection.cursor()

        # Get all subjects from the 'subject' table
        cursor.execute("SELECT subject_code, subject_name FROM subject")
        all_subjects = [{'subject_code': row[0], 'subject_name': row[1]}
                        for row in cursor.fetchall()]

        # Get assessment data for the logged-in faculty
        cursor.execute(
            "SELECT assessment_data FROM faculty_assessment WHERE faculty_id = %s", (faculty_id,))
        result = cursor.fetchone()

        if not result:
            return jsonify({'error': 'No assessment data found for this faculty'}), 404

        # Parse the JSON assessment data to find the relevant subjects and year/branch sections
        assessment_data = json.loads(result[0])

        # Filter the subjects based on the faculty's assessment data
        faculty_subjects = []
        assessments = []
        for subject_code, year_sections in assessment_data.items():
            # Get the subject details from the 'all_subjects' list
            for subject in all_subjects:
                if subject['subject_code'] == subject_code:
                    faculty_subjects.append(subject)
                    assessments.append({
                        'subject_code': subject_code,
                        'year_sections': year_sections
                    })
                    break

        return jsonify({
            'subjects': faculty_subjects,
            'assessments': assessments
        })

    except pymysql.MySQLError as e:
        return jsonify({'error': f"Database error: {e}"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

# mid marks student


@app.route('/get_students_results', methods=['POST'])
def get_students_results():
    try:
        data = request.form.to_dict()
        print("Received Form Data:", data)

        subject_code = request.form['subject']
        year_branch = request.form['year_branch']
        print(f"Subject Code: {subject_code}, Year_Branch: {year_branch}")

        if '-' not in year_branch:
            return jsonify({'error': "Invalid year_branch format. Expected format: 'YYYY-BRANCH SECTION'"}), 400

        passed_out_year, branch_section = year_branch.split('-')

        if ' ' not in branch_section:
            return jsonify({'error': "Invalid branch_section format. Expected format: 'BRANCH SECTION'"}), 400

        branch, section = branch_section.split()
        print(
            f"Extracted Passed Out Year: {passed_out_year}, Branch: {branch}, Section: {section}")

        connection = pymysql.connect(**db_config)
        cursor = connection.cursor(pymysql.cursors.DictCursor)

        # Fetch subject details
        semester_query = """
            SELECT semester, elective, subject_name FROM subject WHERE subject_code = %s
        """
        cursor.execute(semester_query, (subject_code,))
        subject_result = cursor.fetchone()
        print("Subject Query Result:", subject_result)

        if not subject_result:
            return jsonify({'error': f"Subject not found for subject code: {subject_code}"}), 400

        semester = subject_result["semester"]
        is_elective = subject_result["elective"]
        subject_name = subject_result["subject_name"]

        # Check if the subject is elective
        if "Core" in is_elective:
            student_query = """
                SELECT `STUDENT NAME`, roll_number FROM profile 
                WHERE Branch = %s AND Section = %s AND `Passed out year` = %s
            """
            cursor.execute(student_query, (branch, section, passed_out_year))
        else:
            student_query = """
                SELECT p.roll_number, p.`STUDENT NAME`
                FROM profile p
                JOIN student_electives se ON p.roll_number = se.roll_number
                WHERE p.Branch = %s 
                AND p.Section = %s 
                AND p.`Passed out year` = %s
                AND se.subject_name = %s
            """
            cursor.execute(student_query, (branch, section,
                           passed_out_year, subject_name))

        students = cursor.fetchall()
        print("Fetched Students:", students)

        if not students:
            return render_template('no_students.html')

        # Fetch marks data
        marks_query = """
            SELECT roll_number, cie1, cie2, assignment, avg, total 
            FROM internal_marks 
            WHERE subject_code = %s AND semester = %s AND passed_out_year = %s
        """
        cursor.execute(marks_query, (subject_code, semester, passed_out_year))
        marks_data = cursor.fetchall()
        print("Fetched Marks Data:", marks_data)

        marks_dict = {row['roll_number']: row for row in marks_data}

        # Fetch internal marks access settings
        access_query = """
            SELECT component_name, access_status FROM internalmarksaccess
        """
        cursor.execute(access_query)
        access_data = cursor.fetchall()
        print("Access Data:", access_data)

        access_dict = {row['component_name']: row['access_status']
                       for row in access_data}

        return render_template(
            'students_results.html',
            students=students,
            marks_dict=marks_dict,
            access_dict=access_dict,
            subject_code=subject_code,
            subject_name=subject_name,
            semester=semester,
            passed_out_year=passed_out_year,
            branch=branch,
            section=section
        )

    except pymysql.MySQLError as db_error:
        print("Database Error:", str(db_error))
        return jsonify({'error': f"Database error: {db_error}"}), 500
    except ValueError as ve:
        print("Value Error:", str(ve))
        return jsonify({'error': f"Value error: {ve}"}), 500
    except Exception as e:
        print("Unexpected Error:", str(e))
        return jsonify({'error': f"An error occurred: {e}"}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'connection' in locals():
            connection.close()


@app.route('/enter_marks', methods=['POST'])
def submit_marks():
    action = request.form.get('action')

    # Retrieve common form data
    subject_code = request.form.get('subject_code')
    if not subject_code:
        return render_template("Enter_mid_marks_faculty.html", error="Subject code is required!")

    subject_name = request.form.get('subject_name')
    if not subject_name:
        return render_template("Enter_mid_marks_faculty.html", error="Subject name is required!")

    passed_out_year = request.form.get('passed_out_year')
    if not passed_out_year:
        return render_template("Enter_mid_marks_faculty.html", error="Passed out year is required!")

    semester = request.form.get('semester')
    if not semester:
        return render_template("Enter_mid_marks_faculty.html", error="Semester is required!")

    if action == "submit":
        # Logic to upload marks to the database
        marks_data = []
        processed_subjects = set()

        for roll_number in request.form:
            if roll_number.startswith("cie1_"):
                student_roll_number = roll_number.split("_")[1]

                if (student_roll_number, subject_code) in processed_subjects:
                    return render_template(
                        "Enter_mid_marks_faculty.html",
                        error=f"Duplicate entry for roll number {student_roll_number} and subject {subject_code}"
                    )

                cie1 = request.form.get(f"cie1_{student_roll_number}")
                cie2 = request.form.get(f"cie2_{student_roll_number}")
                assignment = request.form.get(
                    f"assignment_{student_roll_number}")
                avg = request.form.get(f"avg_{student_roll_number}")
                total = request.form.get(f"total_{student_roll_number}")

                # Convert to appropriate types or keep as None
                cie1 = int(cie1) if cie1 else None
                cie2 = int(cie2) if cie2 else None
                assignment = int(assignment) if assignment else None
                avg = float(avg) if avg else None
                total = float(total) if total else None

                marks_data.append((student_roll_number, subject_code, subject_name, cie1, cie2, total, assignment, avg,
                                   passed_out_year, semester))
                processed_subjects.add((student_roll_number, subject_code))

        try:
            conn = pymysql.connect(**db_config)
            cursor = conn.cursor()

            insert_update_query = """
            INSERT INTO internal_marks (roll_number, subject_code, subject_name, cie1, cie2, total, assignment, avg, passed_out_year, semester)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        cie1 = COALESCE(VALUES(cie1), cie1),
        cie2 = COALESCE(VALUES(cie2), cie2),
        total = COALESCE(VALUES(total), total),
        assignment = COALESCE(VALUES(assignment), assignment),
        avg = COALESCE(VALUES(avg), avg)

            """
            cursor.executemany(insert_update_query, marks_data)
            conn.commit()

            return render_template("Enter_mid_marks_faculty.html", success="Marks uploaded successfully!")

        except pymysql.IntegrityError as integrity_err:
            return render_template(
                "Enter_mid_marks_faculty.html",
                error=f"Duplicate entry detected: {integrity_err}"
            )
        except pymysql.MySQLError as err:
            print("Error:", err)
            return render_template("Enter_mid_marks_faculty.html", error="Failed to upload marks.")
        finally:
            cursor.close()
            conn.close()

    elif action == "download":
        # Fetch students from the database based on provided parameters
        try:
            conn = pymysql.connect(**db_config)
            cursor = conn.cursor()

            query = """
            SELECT roll_number, subject_code, subject_name, cie1, cie2, assignment, avg, total
            FROM internal_marks
            WHERE subject_code = %s AND passed_out_year = %s AND semester = %s
            """
            cursor.execute(query, (subject_code, passed_out_year, semester))
            students = cursor.fetchall()  # Fetch all matching students
        except pymysql.MySQLError as err:
            return render_template("Enter_mid_marks_faculty.html", error=f"Failed to fetch data for download: {err}")
        finally:
            cursor.close()
            conn.close()

        # Generate Excel file
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet()

        # Write headers
        headers = ['Roll Number', 'Subject Code', 'Subject Name', 'CIE-I',
                   'CIE-II', 'Assignment', 'Average', 'Total', 'Year', 'Semester']
        for col_num, header in enumerate(headers):
            worksheet.write(0, col_num, header)

        # Write data
        for row_num, student in enumerate(students, start=1):
            worksheet.write(row_num, 0, student[0])  # roll_number
            worksheet.write(row_num, 1, student[1])  # subject_code
            worksheet.write(row_num, 2, student[2])  # subject_name
            worksheet.write(
                row_num, 3, student[3] if student[3] is not None else '')  # cie1
            worksheet.write(
                row_num, 4, student[4] if student[4] is not None else '')  # cie2
            worksheet.write(
                row_num, 5, student[5] if student[5] is not None else '')  # assignment
            worksheet.write(
                row_num, 6, student[6] if student[6] is not None else '')  # avg
            worksheet.write(
                row_num, 7, student[7] if student[7] is not None else '')  # total

        workbook.close()
        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name="Marks_Report.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


def add_cache_control(response):
    """Add cache control headers to the response to prevent caching."""
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.before_request
def require_login():
    """Ensure that user is logged in for protected routes."""
    if request.endpoint in ['profile', 'edit_profile', 'academic_result',
                            'change_password'] and 'username' not in session:
        return redirect(url_for('index'))


@app.after_request
def apply_cache_control(response):
    """Apply cache control to all routes."""
    return add_cache_control(response)


@app.after_request
def after_request(response):
    app.logger.info(f'Request: {request.method} {request.path} -> {response.status_code}')
    return response


# Logout route


@app.route('/logout', methods=['POST'])
def logout():
    app.logger.info("Logout initiated")
    session.clear()
    flash("You have been logged out successfully.", "info")
    response = make_response(redirect(url_for('index')))
    return add_cache_control(response)


# Admin page route

# not yet present
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    app.logger.info(f"Session data: {session}")
    if 'username' in session and 'super_admin' in session.get('roles', []):
        app.logger.info(
            f"Admin '{session['username']}' entered the admin page")
        return render_template('admin.html')
    else:
        app.logger.info("User is not authorized or session expired")
        return redirect('/')


@app.route('/eadmin', methods=['GET', 'POST'])
def eadmin():
    if 'username' in session:  # Check if user is logged in
        # Retrieve the username or a default value
        username = session.get('username', 'Unknown User')
        app.logger.info(f"Admin '{username}' entered the eadmin page")
        return render_template('e_admin.html')
    else:
        app.logger.info("User is not authorized or session expired")
        return redirect('/')  # Redirect to login page


@app.route('/admin_student', methods=['GET', 'POST'])
def admin_student():
    # Check if user is logged in
    if 'username' in session and 'super_admin' in session.get('roles', []):
        # Retrieve the username or a default value
        username = session.get('username', 'Unknown User')
        app.logger.info(f"Admin '{username}' entered the admin_student page")
        return render_template('admin_student.html')
    else:
        app.logger.info("User is not authorized or session expired")
        return redirect('/')  # Redirect to login page


@app.route('/admin_faculty', methods=['GET', 'POST'])
def admin_faculty():
    # Check if user is logged in
    if 'username' in session and 'super_admin' in session.get('roles', []):
        # Retrieve the username or a default value
        username = session.get('username', 'Unknown User')
        app.logger.info(f"Admin '{username}' entered the admin_faculty page")
        return render_template('admin_faculty.html')
    else:
        app.logger.info("User is not authorized or session expired")
        return redirect('/')  # Redirect to login page


@app.route('/toggle', methods=['POST'])
def toggle_access():
    error_toggle_access = request.args.get('error_toggle_access')
    success_toggle_access = request.args.get('success_toggle_access')
    active_tab = 'internal_marks_access'
    components = ["CIE1", "CIE2", "Assignment"]
    statuses = {component: 'ON' if request.form.get(
        component) == 'on' else 'OFF' for component in components}

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        for component, status in statuses.items():
            query = """
            UPDATE InternalMarksAccess
            SET access_status = %s, updated_at = NOW()
            WHERE component_name = %s
            """
            cursor.execute(query, (status, component))
        connection.commit()

        # Set the success message after successfully updating
        success_toggle_access = "Access status updated successfully!"

    except Exception as e:
        connection.rollback()
        # Set the error message if an exception occurs
        error_toggle_access = f"An error occurred: {str(e)}"

    finally:
        cursor.close()
        connection.close()

    return render_template(
        'e_admin.html',
        active_tab=active_tab,
        error_toggle_access=error_toggle_access,
        success_toggle_access=success_toggle_access
    )


@app.route('/get_access_status', methods=['GET'])
def get_access_status():
    # Connect to the database
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Fetch current access statuses
        query = "SELECT component_name, access_status FROM InternalMarksAccess"
        cursor.execute(query)
        results = cursor.fetchall()

        # Transform results into the expected format
        statuses = {row['component_name']
            : row['access_status'] == 'ON' for row in results}

        return jsonify({"success": True, "statuses": statuses})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    finally:
        cursor.close()
        connection.close()


@app.route('/add_subject', methods=['GET', 'POST'])
def add_subject():
    if request.method == 'POST':
        subject_code = request.form['subject_code']
        subject_name = request.form['subject_name']

        # Connect to the database and insert the new subject
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO Subject (subject_code, subject_name) VALUES (%s, %s)",
                       (subject_code, subject_name))
        conn.commit()
        cursor.close()
        conn.close()

        return 'Subject added successfully!'

# doubt




@app.route('/get_departments', methods=['GET'])
def get_departments():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Fetch department details along with the HOD name if assigned
        cursor.execute("""
            SELECT d.department_id, d.department_name, 
                   CASE 
                       WHEN d.department_name = 'Non Teaching' THEN NULL 
                       ELSE CONCAT(f.first_name, ' ', f.last_name, ' is assigned as HOD')
                   END AS hod_name
            FROM department d
            LEFT JOIN faculty_user f ON d.department_head = f.faculty_id
        """)
        departments = cursor.fetchall()
        return jsonify(departments)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/admin_action', methods=['POST'])
def admin_action():
    # Check if the user is logged in and has the super_admin role
    if 'username' not in session and 'super_admin' not in session.get('roles', []):
        return render_template('admin.html', error='Unauthorized access'), 401

    # Extract common form inputs
    action = request.form.get('action')
    user_type = request.form.get('user_type')

    password = request.form.get('password')
    roll_start_range = request.form.get('roll_start_range')
    roll_end_range = request.form.get('roll_end_range')
    username = request.form.get('username')
    conn = get_db_connection()
    cursor = conn.cursor()
    response = {}

    try:
        # Function to validate if the username has exactly 12 digits and starts with "2456"

        if action == 'create_single':
            active_tab = request.args.get('active_tab', 'create')
            # Single User Creation
            if user_type == 'student':
                if not username or not password:
                    return render_template('admin.html', active_tab=active_tab, error='Username and password are required for students'), 400
                if not username.startswith('2456') or len(username) != 12:
                    return render_template('admin.html', active_tab=active_tab, error='Invalid student username. Must start with "2456" and be 12 digits long'), 400

                cursor.execute(
                    "SELECT * FROM users WHERE username = %s", (username,))
                if cursor.fetchone():
                    return render_template('admin.html', active_tab=active_tab, error='User already exists'), 400

                hashed_password = generate_password_hash(
                    password, method='scrypt')
                cursor.execute(
                    "INSERT INTO users (username, password, role, original_password) VALUES (%s, %s, %s, %s)",
                    (username, hashed_password, 'student', password)
                )
                conn.commit()
                return render_template('admin.html', active_tab=active_tab, message='Student created successfully.')

            else:
                # Handle faculty/admin creation
                data = request.form
                faculty_id = data.get('faculty_id')
                first_name = data.get('first_name')
                last_name = data.get('last_name')
                email = data.get('email')
                phone_number = data.get('phone_number')
                department_id = data.get('department_id')
                designation = data.get('designation')
                joining_date = data.get('joining_date')
                salary = data.get('salary')
                roles = request.form.getlist('roles[]')
                status = data.get('status')

                # Validation: Ensure all fields are provided
                # Validation
                if not all([faculty_id, first_name, last_name, email, phone_number, department_id, designation,
                            joining_date, salary, roles, status]):
                    print("Missing data fields:", {
                        'faculty_id': faculty_id, 'first_name': first_name, 'last_name': last_name,
                        'email': email, 'phone_number': phone_number, 'department_id': department_id,
                        'designation': designation, 'joining_date': joining_date, 'salary': salary,
                        'roles': roles, 'status': status
                    })
                    return render_template('admin.html', active_tab=active_tab,
                                           error='All fields are required for faculty/admin creation'), 400

                if not faculty_id.isdigit():
                    return render_template('admin.html', active_tab=active_tab, error='Faculty ID must be a numeric value'), 400

                if not department_id:
                    return render_template('admin.html', active_tab=active_tab, error='Please select a valid department'), 400

                try:
                    salary = float(salary)
                except ValueError:
                    return render_template('admin.html', active_tab=active_tab, error='Salary must be a valid number'), 400

                # Check if faculty_id or email already exists
                cursor.execute(
                    "SELECT * FROM faculty_user WHERE faculty_id = %s OR email = %s", (faculty_id, email))

                # Fetch only one record to check if it exists
                existing_user = cursor.fetchone()

                # Ensure the cursor result set is cleared
                if existing_user:
                    # Skip processing if the record already exists
                    cursor.fetchall()  # Clear remaining results if any
                    return render_template('admin.html', active_tab=active_tab, error='Faculty ID or Email already exists'), 400

                session['faculty_data'] = {
                    'faculty_id': faculty_id,
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': email,
                    'phone_number': phone_number,
                    'department_id': department_id,
                    'designation': designation,
                    'joining_date': joining_date,
                    'salary': salary,
                    'roles': roles,
                    'status': status
                }

                # Check for HOD role and ask for confirmation if necessary
                is_hod_confirmed = data.get(
                    'is_hod_confirmed', 'false') == 'true'

                if "hod" in roles:
                    cursor.execute(
                        "SELECT department_head FROM department WHERE department_id = %s", (department_id,))
                    department = cursor.fetchone()

                    if department and department["department_head"]:
                        # Current HOD exists, fetch their name
                        cursor.execute("SELECT first_name, last_name FROM faculty_user WHERE faculty_id = %s",
                                       (department["department_head"],))
                        current_hod = cursor.fetchone()
                        current_hod_name = f"{current_hod['first_name']} {current_hod['last_name']}"
                        hod_message = f"Should we change the HOD from {current_hod_name} to {first_name} {last_name}?"
                    else:
                        # No HOD currently assigned
                        hod_message = f"Should we really assign {first_name} {last_name} as the new HOD?"

                    # Return the template with HOD message for confirmation
                    if not is_hod_confirmed:
                        return render_template("admin.html", active_tab=active_tab, hod_alert=True, hod_message=hod_message, **data)

                    # Insert new faculty/admin into the database
                    password = generate_password_hash(
                        faculty_id, method='scrypt')
                    roles_json = json.dumps(roles)

                    cursor.execute(
                        """
                        INSERT INTO faculty_user (faculty_id, first_name, last_name, email, phone_number, department_id, 
                        designation, joining_date, salary, password, roles, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (faculty_id, first_name, last_name, email, phone_number, department_id, designation,
                         joining_date,
                         salary, password, roles_json, status)
                    )

                    # After inserting, assign the new faculty as the department head if the role is HOD
                    if "hod" in roles:
                        cursor.execute("UPDATE department SET department_head = %s WHERE department_id = %s",
                                       (faculty_id, department_id))

                    conn.commit()
                    return render_template('admin.html', message='Faculty/Admin created and HOD updated successfully.', active_tab=active_tab)

                # If no HOD role selected, insert faculty/admin as usual
                password = generate_password_hash(faculty_id, method='scrypt')
                roles_json = json.dumps(roles)

                cursor.execute(
                    """
                    INSERT INTO faculty_user (faculty_id, first_name, last_name, email, phone_number, department_id, 
                    designation, joining_date, salary, password, roles, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (faculty_id, first_name, last_name, email, phone_number, department_id, designation, joining_date,
                     salary, password, roles_json, status)
                )

                conn.commit()
                return render_template('admin.html', message='Faculty/Admin created successfully.', active_tab=active_tab)

        elif action == 'create_multiple':
            active_tab = request.args.get('active_tab', 'create')
            # Multiple Users Creation
            if not roll_start_range or not roll_end_range:
                return render_template('admin.html', error='Roll start and end ranges are required for multiple user creation', active_tab=active_tab), 400
            if roll_start_range > roll_end_range:
                return render_template(
                    'admin.html',
                    active_tab=active_tab,
                    error='Invalid roll range. Start roll cannot be greater than end roll.'
                ), 400
            start = int(roll_start_range)
            end = int(roll_end_range)
            created_users = []
            existing_users = []

            for roll_number in range(start, end + 1):
                username = str(roll_number)
                password = username  # Set password to roll number

                if not username.startswith('2456') or len(username) != 12:
                    return render_template('admin.html', error='Username must start with "2456" and be 12 digits long', active_tab=active_tab), 400

                cursor.execute(
                    "SELECT * FROM users WHERE username = %s", (username,))
                if cursor.fetchone():
                    existing_users.append(username)
                else:
                    hashed_password = generate_password_hash(
                        password, method='scrypt')
                    cursor.execute(
                        "INSERT INTO users (username, password, role, original_password) VALUES (%s, %s, %s, %s)",
                        (username, hashed_password, 'student', password)
                    )
                    created_users.append(username)

            conn.commit()
            if created_users or existing_users:
                error_message = None
                if existing_users:
                    error_message = f'Error: Users already exist: {", ".join(existing_users)}'

                success_message = None
                if created_users:
                    success_message = f'Success: Users created: {", ".join(created_users)}'
            if not created_users:
                return render_template(
                    'admin.html',
                    active_tab=active_tab,
                    error='Invalid roll range or no new users created. Please check the range and try again.'
                )
            return render_template(
                'admin.html',
                active_tab=active_tab,
                error=error_message,
                message=success_message
            )

    except Exception as e:
        conn.rollback()
        return render_template('admin.html', error=f'An error occurred: {str(e)}', active_tab=active_tab)
    finally:
        cursor.close()
        conn.close()


@app.route('/admin_delete_action', methods=['POST'])
def admin_delete_action():
    active_tab = request.args.get('active_tab', 'delete')
    # Determine single or multiple delete
    action_type = request.form.get('action_type', 'single')
    conn = get_db_connection()
    cursor = conn.cursor()

    def is_valid_student_username(username):
        return len(username) == 12 and username.startswith(('2', '4', '5', '6'))

    def is_valid_faculty_id(faculty_id):
        return faculty_id.isdigit()

    if action_type == 'single':
        username = request.form.get('username')
        faculty_id = request.form.get('faculty_id')
        if username:
            # Check if the user exists
            cursor.execute(
                "SELECT * FROM users WHERE username = %s", (username,))
            existing_user = cursor.fetchone()

            if not existing_user:
                return render_template('admin.html', error_delete=f'User {username} does not exist',
                                       active_tab=active_tab), 404
            if username == 'super_admin':
                return render_template('admin.html', error_delete='Super admin cannot be deleted',
                                       active_tab=active_tab), 403
            if not is_valid_student_username(username):
                return render_template('admin.html',
                                       error_delete='Username must be 12 digits and start with "2456" for student role',
                                       active_tab=active_tab), 400

            cursor.execute(
                "DELETE FROM users WHERE username = %s", (username,))
            conn.commit()
            return render_template('admin.html', success_delete=f'User {username} deleted successfully',
                                   active_tab=active_tab)

        elif faculty_id:
            if not is_valid_faculty_id(faculty_id):
                return render_template('admin.html',
                                       error_delete='Faculty ID must be 6 digits',
                                       active_tab=active_tab), 400

            # Check if the faculty exists
            cursor.execute(
                "SELECT * FROM faculty_user WHERE faculty_id = %s", (faculty_id,))
            existing_faculty = cursor.fetchone()

            if not existing_faculty:
                return render_template('admin.html', error_delete=f'Faculty {faculty_id} does not exist',
                                       active_tab=active_tab), 404

            # Check if the faculty is inactive
            if existing_faculty['status'].lower() == 'inactive':
                return render_template('admin.html', error_delete=f'Inactive faculty {faculty_id} cannot be deleted',
                                       active_tab=active_tab), 403

            cursor.execute(
                "DELETE FROM faculty_user WHERE faculty_id = %s", (faculty_id,))
            conn.commit()
            return render_template('admin.html', success_delete=f'Faculty {faculty_id} deleted successfully',
                                   active_tab=active_tab)

    elif action_type == 'multiple':
        roll_start = request.form.get('roll_start')
        roll_end = request.form.get('roll_end')

        if not roll_start or not roll_end or roll_start > roll_end:
            return render_template('admin.html', error_delete='Roll number range not specified or invalid range',
                                   active_tab=active_tab), 400

        # Generate the roll number range
        try:
            roll_numbers = [str(i) for i in range(
                int(roll_start), int(roll_end) + 1)]
        except ValueError:
            return render_template('admin.html', error_delete='Invalid roll number range', active_tab=active_tab), 400

        # Validate and delete users
        deleted_users = []
        non_existing_users = []
        for roll_number in roll_numbers:
            if not is_valid_student_username(roll_number):
                non_existing_users.append(roll_number)
                continue

            cursor.execute(
                "SELECT * FROM users WHERE username = %s", (roll_number,))
            if cursor.fetchone():
                cursor.execute(
                    "DELETE FROM users WHERE username = %s", (roll_number,))
                deleted_users.append(roll_number)
            else:
                non_existing_users.append(roll_number)

        conn.commit()

        success_message = f"Deleted users: {', '.join(deleted_users)}" if deleted_users else "No users deleted."
        error_message = f"Non-existing users: {', '.join(non_existing_users)}" if non_existing_users else ""

        return render_template('admin.html',
                               success_delete=success_message,
                               error_delete=error_message,
                               active_tab=active_tab)

    return render_template('admin.html', error_delete='Invalid action type', active_tab=active_tab), 400


@app.route('/confirm_hod', methods=['POST'])
def confirm_hod():
    active_tab = request.args.get('active_tab', 'create')
    conn = get_db_connection()
    cursor = conn.cursor()
    # Retrieve data from session
    faculty_data = session.get('faculty_data')

    if not faculty_data:
        # Return to the form if no data is found
        return redirect(url_for('admin_action'))

    # Extract the saved form data
    faculty_id = faculty_data['faculty_id']
    first_name = faculty_data['first_name']
    last_name = faculty_data['last_name']
    email = faculty_data['email']
    phone_number = faculty_data['phone_number']
    department_id = faculty_data['department_id']
    designation = faculty_data['designation']
    joining_date = faculty_data['joining_date']
    salary = faculty_data['salary']
    roles = faculty_data['roles']
    status = faculty_data['status']

    # Check if HOD confirmation is true
    is_hod_confirmed = request.form.get('is_hod_confirmed') == 'true'

    if is_hod_confirmed and "hod" in roles:
        # Get the current HOD (department_head) from the department table
        cursor.execute(
            "SELECT department_head FROM department WHERE department_id = %s", (department_id,))
        department = cursor.fetchone()

        if department and department["department_head"]:
            current_hod_id = department["department_head"]

            # Remove the "hod" role from the current HOD in faculty_user table
            cursor.execute(
                "SELECT roles FROM faculty_user WHERE faculty_id = %s", (current_hod_id,))
            current_hod_roles = cursor.fetchone()

            if current_hod_roles:
                # Decode the JSON roles
                roles_list = json.loads(current_hod_roles["roles"])

                if "hod" in roles_list:
                    roles_list.remove("hod")

                    # Update the roles for the previous HOD
                    cursor.execute(
                        "UPDATE faculty_user SET roles = %s WHERE faculty_id = %s",
                        (json.dumps(roles_list), current_hod_id)
                    )

        # Insert the new faculty member into the faculty_user table
        password = generate_password_hash(faculty_id, method='scrypt')
        roles_json = json.dumps(roles)

        cursor.execute(
            """
            INSERT INTO faculty_user (faculty_id, first_name, last_name, email, phone_number, department_id, 
            designation, joining_date, salary, password, roles, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (faculty_id, first_name, last_name, email, phone_number, department_id, designation, joining_date,
             salary, password, roles_json, status)
        )

        # If HOD is confirmed, update the department head
        cursor.execute("UPDATE department SET department_head = %s WHERE department_id = %s",
                       (faculty_id, department_id))

        conn.commit()

        # Clear the session after successful submission
        session.pop('faculty_data', None)

        return render_template('admin.html', message='Faculty/Admin created and HOD assigned successfully.', active_tab=active_tab)

    else:
        return render_template('admin.html', error='HOD confirmation failed or invalid role.', active_tab=active_tab)


# Define the route for adding a course
@app.route('/create_course', methods=['POST'])
def add_course():
    conn = get_db_connection()
    cursor = conn.cursor()
    error_add_subject = request.args.get('error_add_subject')
    success_add_subject = request.args.get('success_add_subject')
    active_tab = request.args.get('active_tab', 'add_subject')

    data = request.form
    subject_name = data.get('subject_name')
    subject_code = data.get('subject_code')
    department_id = data.get('department_id')
    semester = data.get('semester')
    credits = data.get('credits')
    # Default to 'Core' if nothing is selected
    elective = data.get('elective', 'Core')

    # Validation
    if not all([subject_name, subject_code, department_id, semester, credits, elective]):
        error_add_subject = "All fields are required"
        return render_template('hod.html', error_add_subject=error_add_subject, success_add_subject=success_add_subject, active_tab=active_tab)

    try:
        # Check if subject_code already exists
        cursor.execute(
            "SELECT 1 FROM subject WHERE subject_code = %s", (subject_code,))
        if cursor.fetchone():
            error_add_subject = "Course code already exists."
            return render_template('hod.html', error_add_subject=error_add_subject, success_add_subject=success_add_subject, active_tab=active_tab)

        # Insert the new course with elective type
        cursor.execute("""
            INSERT INTO subject (subject_name, subject_code, department_id, semester, credits, elective)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (subject_name, subject_code, department_id, semester, credits, elective))
        conn.commit()
        success_add_subject = "Course added successfully."
    except Exception as e:
        conn.rollback()
        error_add_subject = f"Error adding course: {str(e)}"
    finally:
        cursor.close()
        conn.close()

    return render_template('hod.html', error_add_subject=error_add_subject, success_add_subject=success_add_subject, active_tab=active_tab)


@app.route('/faculty_users_update', methods=['GET', 'POST'])
def faculty_update():
    error = request.args.get('error')
    success = request.args.get('success')
    faculty = None
    active_tab = request.args.get('active_tab', 'faculty_users_update')
    departments = []

    if request.method == 'POST':
        faculty_id = request.form.get('faculty_id')

        # Validation for Faculty ID
        if not faculty_id or not faculty_id.isdigit():
            error = "Please enter a valid Faculty ID."
        else:
            # Connect to the database
            conn = get_db_connection()
            cursor = conn.cursor()

            # Fetch faculty details
            cursor.execute(
                "SELECT * FROM faculty_user WHERE faculty_id = %s", (faculty_id,))
            faculty = cursor.fetchone()

            # Fetch departments for the dropdown
            cursor.execute("SELECT * FROM department")
            departments = cursor.fetchall()

            cursor.close()
            conn.close()

            if not faculty:
                error = "Faculty ID not found."
            else:
                # Convert JSON roles to Python list for rendering in checkboxes
                faculty['roles'] = json.loads(
                    faculty['roles']) if faculty['roles'] else []

    return render_template(
        'admin_faculty.html',
        error=error,
        success=success,
        faculty=faculty,
        active_tab=active_tab,
        departments=departments  # Pass the departments to the template
    )


@app.route('/update_faculty', methods=['POST'])
def update_faculty():
    error = None
    success = None

    # Retrieve updated form data
    updated_data = {
        'faculty_id': request.form.get('faculty_id'),
        'first_name': request.form.get('first_name'),
        'last_name': request.form.get('last_name'),
        'email': request.form.get('email'),
        'phone_number': request.form.get('phone_number'),
        'department_id': request.form.get('department_id'),
        'designation': request.form.get('designation'),
        'joining_date': request.form.get('joining_date'),
        'salary': request.form.get('salary'),
        'roles': json.dumps(request.form.getlist('roles[]')),
        'status': request.form.get('status')
    }

    try:
        # Connect to the database
        conn = get_db_connection()
        cursor = conn.cursor()

        # Debug incoming data
        print("Updated Data:", updated_data)

        # Parse roles and check for HOD (case-insensitive)
        roles = json.loads(updated_data['roles']) if updated_data['roles'] else []
        is_hod = 'hod' in [role.lower() for role in roles]  # Case-insensitive check
        print("Parsed Roles:", roles)
        print("HOD Status:", is_hod)

        # Fetch the current department head for this department
        cursor.execute(
            "SELECT department_head FROM department WHERE department_id = %s",
            (updated_data['department_id'],)
        )
        current_department_head = cursor.fetchone()
        print("Current Department Head:", current_department_head)

        # If setting to inactive and currently a HOD, remove HOD role
        if updated_data['status'] == 'inactive' and current_department_head and current_department_head[0] == int(updated_data['faculty_id']):
            # Remove HOD from roles
            roles = [role for role in roles if role.lower() != 'hod']
            updated_data['roles'] = json.dumps(roles)
            
            # Remove as department head
            cursor.execute(
                "UPDATE department SET department_head = NULL WHERE department_id = %s",
                (updated_data['department_id'],)
            )

        # Update faculty_user table
        update_query = """
        UPDATE faculty_user 
        SET first_name = %(first_name)s, 
            last_name = %(last_name)s, 
            email = %(email)s, 
            phone_number = %(phone_number)s, 
            department_id = %(department_id)s, 
            designation = %(designation)s, 
            joining_date = %(joining_date)s, 
            salary = %(salary)s, 
            roles = %(roles)s, 
            status = %(status)s
        WHERE faculty_id = %(faculty_id)s
        """
        cursor.execute(update_query, updated_data)
        print("Faculty details updated successfully.")

        # Handle HOD update logic only if status is active
        if updated_data['status'] == 'active':
            if is_hod:
                print(f"Assigning faculty_id {updated_data['faculty_id']} as HOD for department {updated_data['department_id']}")
                cursor.execute(
                    "UPDATE department SET department_head = %s WHERE department_id = %s",
                    (updated_data['faculty_id'], updated_data['department_id'])
                )
            elif current_department_head and current_department_head[0] == int(updated_data['faculty_id']):
                print(f"Removing faculty_id {updated_data['faculty_id']} as HOD for department {updated_data['department_id']}")
                cursor.execute(
                    "UPDATE department SET department_head = NULL WHERE department_id = %s",
                    (updated_data['department_id'],)
                )

        # Commit changes
        conn.commit()
        success = "Faculty details and department head updated successfully!"

    except Exception as e:
        error = f"An error occurred: {str(e)}"
        print("Error:", error)
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return render_template('admin_faculty.html', error=error, success=success)


@app.route('/add_department', methods=['GET', 'POST'])
def add_department():
    error_create_department = None
    success_create_department = None
    active_tab = 'add_department'

    if request.method == 'POST':
        # Handle form submission
        department_id = request.form.get('department_id', '').strip()
        department_name = request.form.get('department_name', '').strip()
        department_head = request.form.get('department_head', '').strip()

        # Validate and process input
        if not department_id or len(department_id) != 3:
            error_create_department = "Department ID is required and must be exactly 3 characters."
        elif not department_name:
            error_create_department = "Department name is required."
        elif department_head and not department_head.isdigit():
            error_create_department = "Department Head must be a numeric Faculty ID or left blank."
        else:
            try:
                # Connect to the database
                connection = pymysql.connect(**db_config)
                cursor = connection.cursor()

                # Insert department
                insert_query = """
                    INSERT INTO department (department_id, department_name, department_head)
                    VALUES (%s, %s, %s)
                """
                cursor.execute(insert_query, (department_id,
                               department_name, department_head or None))
                connection.commit()
                success_create_department = f"Department '{department_name}' with ID '{department_id}' added successfully!"
            except pymysql.IntegrityError as e:
                if "Duplicate entry" in str(e):
                    error_create_department = f"Department ID '{department_id}' or name '{department_name}' already exists."
                else:
                    error_create_department = "Database error occurred."
            except Exception as e:
                error_create_department = f"An unexpected error occurred: {e}"
            finally:
                if cursor:
                    cursor.close()
                if connection:
                    connection.close()

    # Fetch updated departments
    departments = []
    try:
        connection = pymysql.connect(**db_config)
        cursor = connection.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT * FROM department")
        departments = cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

    return render_template(
        'admin_faculty.html',
        departments=departments,
        active_tab=active_tab,
        error_create_department=error_create_department,
        success_create_department=success_create_department
    )


@app.route('/delete_department', methods=['POST'])
def delete_department():
    department_id = request.form.get('department_id', '').strip()
    error_delete_department = None
    success_delete_department = None
    active_tab = 'add_department'

    if not department_id or not department_id.isdigit():
        error_delete_department = "Invalid Department ID provided."
    else:
        try:
            # Connect to the database
            connection = pymysql.connect(**db_config)
            cursor = connection.cursor(pymysql.cursors.DictCursor)

            # Validate if the department exists
            cursor.execute(
                "SELECT * FROM department WHERE department_id = %s", (department_id,))
            department = cursor.fetchone()

            if not department:
                error_delete_department = f"No department found with ID {department_id}."
            else:
                # Delete the department
                cursor.execute(
                    "DELETE FROM department WHERE department_id = %s", (department_id,))
                connection.commit()
                success_delete_department = f"Department with ID {department_id} deleted successfully!"
        except Exception as e:
            error_delete_department = f"An error occurred: {e}"
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    # Fetch updated departments to re-render the page
    departments = []
    try:
        connection = pymysql.connect(**db_config)
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM department")
        departments = cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

    # Render the template with updated data and messages
    return render_template(
        'admin_faculty.html',
        departments=departments,
        active_tab=active_tab,
        error_delete_department=error_delete_department,
        success_delete_department=success_delete_department,
        error_create_department=None,
        success_create_department=None
    )


@app.route('/scrape', methods=['POST'])
def scrape():
    logger.debug("Entered the '/scrape' route.")
    error_scrape = request.args.get('error_scrape')
    success_scrape = request.args.get('success_scrape')
    active_tab = 'scrape_results'

    url = request.form['url']
    subject_code_start = int(request.form['subject_code_start'])
    subject_code_end = int(request.form['subject_code_end'])
    letter_range = [chr(i) for i in range(ord('A'), ord('Z') + 1)]

    logger.debug(f"Received URL: {url}")
    logger.debug(
        f"Subject code range: {subject_code_start} to {subject_code_end}")

    def is_valid_student_username(roll_number):
        return len(str(roll_number)) == 12 and str(roll_number).startswith('2456')

    roll_numbers = []
    invalid_ranges = []

    if not url.startswith(('http://', 'https://')):
        error_scrape = "The provided URL is invalid. It must start with http:// or https://."
        logger.error(error_scrape)
        return render_template(
            'admin_student.html' if 'super_admin' in session.get(
                'roles', []) else 'e_admin.html',
            active_tab=active_tab,
            error_scrape=error_scrape
        )

    roll_start_mid = request.form.getlist('roll_start_mid[]')
    roll_end_mid = request.form.getlist('roll_end_mid[]')

    for roll_start, roll_end in zip(roll_start_mid, roll_end_mid):
        try:
            roll_start = int(roll_start)
            roll_end = int(roll_end)
            if roll_start > roll_end:
                return render_template(
                    'admin_student.html',
                    active_tab=active_tab,
                    error_scrape='Invalid roll range. Start roll cannot be greater than end roll.'
                ), 400
            logger.debug(f"Processing range: {roll_start} to {roll_end}")

            for roll in range(roll_start, roll_end + 1):
                if not is_valid_student_username(roll):
                    logger.warning(
                        f"Invalid roll number detected: {roll} in range {roll_start}-{roll_end}")
                    invalid_ranges.append((roll_start, roll_end))
                    break

            if (roll_start, roll_end) not in invalid_ranges:
                roll_numbers.extend(range(roll_start, roll_end + 1))

        except ValueError as e:
            logger.error(
                f"ValueError while processing range {roll_start} to {roll_end}: {e}")
            continue

    logger.debug(f"Valid roll numbers collected: {roll_numbers}")
    logger.debug(f"Invalid ranges detected: {invalid_ranges}")

    if invalid_ranges:
        invalid_ranges_str = ", ".join(
            [f"{start}-{end}" for start, end in invalid_ranges])
        error_scrape = f"The following roll number ranges are invalid: {invalid_ranges_str}. Roll numbers must be 12 digits and start with '2456'."
        logger.error(error_scrape)
        return render_template(
            'admin_student.html' if 'super_admin' in session.get(
                'roles', []) else 'e_admin.html',
            active_tab=active_tab,
            error_scrape=error_scrape,
            success_scrape=success_scrape
        )

    if not roll_numbers:
        error_scrape = "No valid roll number ranges provided."
        logger.error(error_scrape)
        return render_template(
            'admin_student.html' if 'super_admin' in session.get(
                'roles', []) else 'e_admin.html',
            active_tab=active_tab,
            error_scrape=error_scrape,
        )

    logger.debug(
        "Calling scrape_ou_results() with roll numbers and subject codes.")
    results_by_semester = scrape_ou_results(
        url, roll_numbers, subject_code_start, subject_code_end, letter_range)
    logger.debug(f"Scraped results: {results_by_semester}")

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for semester_num in range(1, 9):
            semester_name = f"Semester{semester_num}"
            logger.debug(f"Processing data for {semester_name}")

            semester_data = []
            semester_subjects = set()

            for roll_number in roll_numbers:
                subject_data = {"Roll Number": roll_number, "SGPA": ""}

                if semester_name in results_by_semester:
                    subjects = results_by_semester[semester_name]
                    has_data_for_roll_number = False

                    for subject in subjects:
                        if subject["Roll Number"] == roll_number:
                            has_data_for_roll_number = True
                            subject_name = subject["Subject Name"]
                            semester_subjects.add(subject_name)
                            subject_data[f"{subject_name} Grade Secured"] = subject["Grade Secured"]
                            subject_data[f"{subject_name} Grade Point"] = subject["Grade Point"]
                            subject_data[f"{subject_name} Credits"] = subject["Credits"]
                            subject_data[f"{subject_name} Subject Code"] = subject["Subject Code"]
                            subject_data["SGPA"] = subject["SGPA"]

                    if has_data_for_roll_number:
                        semester_data.append(subject_data)

            if semester_subjects and semester_data:
                semester_df = pd.DataFrame(semester_data)
                headers = ["Roll Number", "SGPA"]
                for subject_name in semester_subjects:
                    headers.extend([
                        f"{subject_name} Grade Secured",
                        f"{subject_name} Grade Point",
                        f"{subject_name} Credits",
                        f"{subject_name} Subject Code"
                    ])
                semester_df = semester_df[headers]
                logger.debug(f"Writing data to Excel sheet: {semester_name}")
                semester_df.to_excel(
                    writer, sheet_name=semester_name, index=False)

    output.seek(0)
    logger.debug("Excel file created successfully. Sending file for download.")
    return send_file(output, as_attachment=True, download_name="SGPA_Results_by_Semester.xlsx")


def calculate_sgpa(semester_table, roll_number):
    connection = pymysql.connect(**db_config)
    query = f"""
    SELECT SUM(credits * grade_point) / SUM(credits) AS sgpa
    FROM {semester_table}
    WHERE roll_number = %s AND credits > 0
    """
    with connection.cursor() as cursor:
        cursor.execute(query, (roll_number,))
        result = cursor.fetchone()
    connection.close()

    return round(result[0], 2) if result[0] is not None else 0.00


def calculate_total_credits(semester_table, roll_number):
    connection = pymysql.connect(**db_config)
    query = f"""
    SELECT SUM(credits) AS total_credits
    FROM {semester_table}
    WHERE roll_number = %s AND grade_secured != 'F'
    """
    with connection.cursor() as cursor:
        cursor.execute(query, (roll_number,))
        result = cursor.fetchone()
    connection.close()

    return result[0] if result[0] is not None else 0


def calculate_no_of_backlogs(semester_table, roll_number):
    connection = pymysql.connect(**db_config)
    query = f"""
    SELECT COUNT(*) AS backlog_count
    FROM {semester_table}
    WHERE roll_number = %s AND (grade_secured = 'F' OR grade_secured = 'Ab')
    """
    with connection.cursor() as cursor:
        cursor.execute(query, (roll_number,))
        result = cursor.fetchone()
    connection.close()

    return result[0] if result[0] is not None else 0


def store_sgpa_in_db(roll_number):
    connection = pymysql.connect(**db_config)

    sgpas = {}
    total_credits = 0
    total_backlogs = 0
    actual_sgpas = {}  # Dictionary to hold semX_actual_sgpa values
    existing_sgpa = None

    with connection.cursor() as cursor:

        # Fetch existing data from sgpa_cgpa table
        cursor.execute(
            "SELECT * FROM sgpa_cgpa WHERE roll_number = %s", (roll_number,))
        existing_sgpa = cursor.fetchone()

    # Calculate SGPA for each semester and fetch actual SGPA from database
    for i in range(1, 9):
        semester_table = f'sem{i}'
        sgpas[f'sem{i}_sgpa'] = calculate_sgpa(semester_table, roll_number)
        total_credits += calculate_total_credits(semester_table, roll_number)
        total_backlogs += calculate_no_of_backlogs(semester_table, roll_number)

        # Fetch actual SGPA if it exists in the sgpa_cgpa table
        if existing_sgpa:
            for i in range(1, 9):
                # Find the index of the actual SGPA column for each semester
                # Assuming 'semX_actual_sgpa' columns are at positions 7 to 14 in the tuple
                actual_sgpa_col_index = 9 + i
                actual_sgpas[f'sem{i}_actual_sgpa'] = existing_sgpa[
                    actual_sgpa_col_index] if existing_sgpa[actual_sgpa_col_index] is not None else None

    # Calculate CGPA using calculated SGPA values (semX_sgpa)
    total_sgpa = sum(float(sgpas[f'sem{i}_sgpa']) for i in range(
        1, 9) if sgpas[f'sem{i}_sgpa'] is not None)
    cgpa = round(total_sgpa / 8, 2) if total_sgpa else 0.00

    # Insert or update SGPA, CGPA, total credits, number of backlogs, and actual SGPA in the sgpa_cgpa table
    with connection.cursor() as cursor:
        if existing_sgpa:  # If entry exists, update it
            cursor.execute(
                """
                UPDATE sgpa_cgpa
                SET 
                    sem1_sgpa=%s, sem2_sgpa=%s, sem3_sgpa=%s, sem4_sgpa=%s, 
                    sem5_sgpa=%s, sem6_sgpa=%s, sem7_sgpa=%s, sem8_sgpa=%s, 
                    sem1_actual_sgpa=%s, sem2_actual_sgpa=%s, sem3_actual_sgpa=%s, sem4_actual_sgpa=%s,
                    sem5_actual_sgpa=%s, sem6_actual_sgpa=%s, sem7_actual_sgpa=%s, sem8_actual_sgpa=%s,
                    cgpa=%s, total_credits=%s, no_of_backlogs=%s
                WHERE roll_number=%s
                """,
                (
                    sgpas['sem1_sgpa'], sgpas['sem2_sgpa'], sgpas['sem3_sgpa'], sgpas['sem4_sgpa'],
                    sgpas['sem5_sgpa'], sgpas['sem6_sgpa'], sgpas['sem7_sgpa'], sgpas['sem8_sgpa'],
                    actual_sgpas.get('sem1_actual_sgpa'), actual_sgpas.get(
                        'sem2_actual_sgpa'),
                    actual_sgpas.get('sem3_actual_sgpa'), actual_sgpas.get(
                        'sem4_actual_sgpa'),
                    actual_sgpas.get('sem5_actual_sgpa'), actual_sgpas.get(
                        'sem6_actual_sgpa'),
                    actual_sgpas.get('sem7_actual_sgpa'), actual_sgpas.get(
                        'sem8_actual_sgpa'),
                    cgpa, total_credits, total_backlogs, roll_number
                )
            )
        else:  # If entry does not exist, insert it
            cursor.execute(
                """
                INSERT INTO sgpa_cgpa (
                    roll_number, sem1_sgpa, sem2_sgpa, sem3_sgpa, sem4_sgpa, 
                    sem5_sgpa, sem6_sgpa, sem7_sgpa, sem8_sgpa, 
                    sem1_actual_sgpa, sem2_actual_sgpa, sem3_actual_sgpa, sem4_actual_sgpa,
                    sem5_actual_sgpa, sem6_actual_sgpa, sem7_actual_sgpa, sem8_actual_sgpa,
                    cgpa, total_credits, no_of_backlogs
                ) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    roll_number,
                    sgpas['sem1_sgpa'], sgpas['sem2_sgpa'], sgpas['sem3_sgpa'], sgpas['sem4_sgpa'],
                    sgpas['sem5_sgpa'], sgpas['sem6_sgpa'], sgpas['sem7_sgpa'], sgpas['sem8_sgpa'],
                    actual_sgpas.get('sem1_actual_sgpa'), actual_sgpas.get(
                        'sem2_actual_sgpa'),
                    actual_sgpas.get('sem3_actual_sgpa'), actual_sgpas.get(
                        'sem4_actual_sgpa'),
                    actual_sgpas.get('sem5_actual_sgpa'), actual_sgpas.get(
                        'sem6_actual_sgpa'),
                    actual_sgpas.get('sem7_actual_sgpa'), actual_sgpas.get(
                        'sem8_actual_sgpa'),
                    cgpa, total_credits, total_backlogs
                )
            )

    connection.commit()
    connection.close()


def fetch_current_grade(roll_number, subject_code):
    # Determine the semester based on the subject code or other criteria
    semester = determine_semester(subject_code)
    if semester is None:
        return None  # Handle invalid semester

    # Create a connection to the database
    connection = pymysql.connect(
        host='localhost',
        user='root',
        password='ammu2007',  # Update with your actual password
        database='user_management'  # Your database name
    )

    try:
        with connection.cursor() as cursor:
            # Construct the table name based on the semester
            table_name = f"sem{semester}"

            # Query to fetch the current grade for the given roll number and subject code
            query = f"""
            SELECT grade_secured 
            FROM {table_name}  # Use the constructed table name
            WHERE roll_number = %s AND subject_code = %s
            """
            cursor.execute(query, (roll_number, subject_code))
            current_grade = cursor.fetchone()
            return current_grade[0] if current_grade else None
    finally:
        connection.close()


def calculate_passed_out_year(roll_number):
    roll_number_str = str(roll_number)
    if len(roll_number_str) >= 6:
        year_part = int(roll_number_str[4:6])
        return int(f"20{year_part}") + 4
    else:
        raise ValueError(f"Invalid roll number format: {roll_number}")

# Route for uploading results


def clean_data(value):
    if pd.isna(value) or value == '':
        return None  # Convert NaN or empty strings to None (MySQL NULL)
    return value


@app.route('/upload_results', methods=['POST'])
def upload_results():
    error_upload_results = request.args.get('error_upload_results')
    success_upload_results = request.args.get('success_upload_results')
    active_tab = 'upload_results'

    if 'excel_file' not in request.files:
        error_upload_results = "No file uploaded"
        if 'super_admin' in session.get('roles', []):
            return render_template(
                'admin_student.html',
                active_tab=active_tab,
                error_upload_results=error_upload_results,
            )
        elif 'e-admin' in session.get('roles', []):
            return render_template(
                'e_admin.html',
                active_tab=active_tab,
                error_upload_results=error_upload_results,
            )

    excel_file = request.files['excel_file']

    if excel_file.filename == '':
        error_upload_results = "No selected file"
        if 'super_admin' in session.get('roles', []):
            return render_template(
                'admin_student.html',
                active_tab=active_tab,
                error_upload_results=error_upload_results,
            )
        elif 'e-admin' in session.get('roles', []):
            return render_template(
                'e_admin.html',
                active_tab=active_tab,
                error_upload_results=error_upload_results,
            )

    try:
        results = []
        excel_data = pd.read_excel(BytesIO(excel_file.read()), sheet_name=None)
        # Validate each sheet for required columns and SGPA data
        sgpa_updates = {}

        for sheet_name, df in excel_data.items():
            df.columns = df.columns.str.strip()  # Normalize column names

            # Check if the required SGPA column exists for this semester
            sgpa_column = 'SGPA'
            if sgpa_column not in df.columns:
                continue  # Skip if SGPA column is missing

            # Process SGPA data for each student
            for index, row in df.iterrows():
                roll_number = str(row['Roll Number']).strip()
                sgpa_value = row[sgpa_column]

                # Skip invalid roll numbers or SGPA values
                if pd.isna(roll_number) or pd.isna(sgpa_value):
                    continue

                # Convert SGPA to string to preserve its original format
                sgpa_as_string = str(sgpa_value).strip()

                # Determine the semester from the sheet name
                semester_number = extract_semester_from_sheet(sheet_name)

                if semester_number is None:
                    continue

                # Insert the SGPA value (as it is) into the semX_actual_sgpa column
                sgpa_updates[roll_number] = sgpa_updates.get(roll_number, {})
                sgpa_updates[roll_number][f'sem{semester_number}_actual_sgpa'] = sgpa_as_string

        # Store results from all sheets (updated SGPA values from the Excel file)
        connection = pymysql.connect(**db_config)
        with connection.cursor() as cursor:
            for roll_number, sem_data in sgpa_updates.items():
                sem_actual_sgpa_columns = [
                    f'sem{i}_actual_sgpa' for i in range(1, 9)
                ]
                actual_sgpa_values = []

                for col in sem_actual_sgpa_columns:
                    # Directly take the raw value from sgpa_updates
                    raw_value = sem_data.get(col, None)
                    # Append as-is (None if no value)
                    actual_sgpa_values.append(raw_value)

                # Insert/update semX_actual_sgpa values (store the value directly)
                cursor.execute(
                    f"""
                    INSERT INTO sgpa_cgpa (roll_number, {', '.join(sem_actual_sgpa_columns)})
                    VALUES (%s, {', '.join(['%s'] * len(sem_actual_sgpa_columns))})
                    ON DUPLICATE KEY UPDATE
                    {', '.join([f'{col} = VALUES({col})' for col in sem_actual_sgpa_columns])}
                    """,
                    (roll_number, *actual_sgpa_values)
                )
                connection.commit()
                cursor.execute(
                    "SELECT * FROM sgpa_cgpa WHERE roll_number = %s", (roll_number,))
                result = cursor.fetchone()
        failed_records = {}

        # Fetch existing records with grade_secured = "F"
        connection = pymysql.connect(**db_config)
        with connection.cursor() as cursor:
            for semester in range(1, 9):
                table_name = f"sem{semester}"
                cursor.execute(f"""
                    SELECT roll_number, subject_code, subject_name, grade_secured, grade_point, credits
                    FROM {table_name}
                    WHERE grade_secured = 'F'
                """)
                for roll_number, subject_code, subject_name, grade_secured, grade_point, credits in cursor.fetchall():
                    roll_number = str(roll_number)
                    if roll_number not in failed_records:
                        failed_records[roll_number] = {}
                    failed_records[roll_number][subject_code] = {
                        "subject_name": subject_name,
                        "grade_secured": grade_secured,
                        "grade_point": grade_point,
                        "credits": credits
                    }

        for sheet_name, df in excel_data.items():
            semester = extract_semester_from_sheet(sheet_name)
            if semester is None:
                continue

            uploaded_roll_subjects = set()
            for index, row in df.iterrows():
                roll_number = str(row['Roll Number'])
                passed_out_year = calculate_passed_out_year(roll_number)

                for column in df.columns:
                    if 'Subject Code' in column:
                        subject_name = column.split(' Subject Code')[0]
                        subject_code = row[column]

                        if pd.isna(subject_code):
                            continue

                        if isinstance(subject_code, float) and subject_code.is_integer():
                            subject_code = str(int(subject_code))
                        else:
                            subject_code = str(subject_code)

                        uploaded_roll_subjects.add((roll_number, subject_code))

                        grade_secured_column = f'{subject_name} Grade Secured'
                        grade_secured = row.get(grade_secured_column)
                        grade_point = row.get(f'{subject_name} Grade Point')
                        credits = row.get(f'{subject_name} Credits')

                        semester = determine_semester(subject_code)
                        if semester is None:
                            continue
                        if roll_number in failed_records:
                            # print(
                            #     f"Found roll_number {roll_number} in failed_records.")
                            if subject_code in failed_records[roll_number]:
                                # print(
                                #     f"Found subject_code {subject_code} under roll_number {roll_number} in failed_records.")

                                # Pop the subject code
                                failed_records[roll_number].pop(
                                    subject_code, None)
                                # print(
                                #     f"Popped subject_code {subject_code} for roll_number {roll_number}")

                                # Check if the roll_number has no remaining subjects
                                if not failed_records[roll_number]:
                                    failed_records.pop(roll_number, None)
                                    # print(
                                    #     f"Removed roll_number {roll_number} from failed_records as all subjects are processed.")
                        current_grade = fetch_current_grade(
                            roll_number, subject_code)
                        if current_grade is None:
                            exam_series = 'Regular'

                        elif current_grade.strip() == 'F' and grade_secured != 'F':
                            exam_series = 'Revaluation'
                        elif current_grade.strip() == 'F' and grade_secured == 'F':
                            exam_series = 'Supply'
                        elif current_grade.strip() != 'F' and grade_secured != 'F' and current_grade.strip() != grade_secured:
                            exam_series = 'Revaluation'
                        elif grade_secured.strip().lower() == 'ab':  # Case-insensitive check for "Absent"
                            exam_series = 'Supply'
                        else:
                            exam_series = 'Regular'
                        result = {
                            'roll_number': roll_number,
                            'passed_out_year': passed_out_year,
                            'subject_code': subject_code,
                            'subject_name': subject_name,
                            'credits': credits,
                            'grade_secured': grade_secured,
                            'grade_point': grade_point,
                            'semester': semester,
                            'exam_series': exam_series
                        }
                        results.append(result)

            # Handle records still in failed_records but not in the uploaded file
            for roll_number, subjects in failed_records.items():
                for subject_code, details in subjects.items():
                    results.append({
                        'roll_number': roll_number,
                        'subject_code': subject_code,
                        'subject_name': details['subject_name'],
                        'grade_secured': details['grade_secured'],
                        'grade_point': details['grade_point'],
                        'credits': details['credits'],
                        'exam_series': 'Supply'
                    })

            store_results_in_db(results)
            results = []

        for roll_number in df['Roll Number'].unique():
            store_sgpa_in_db(roll_number)

        success_upload_results = "Results and SGPA data uploaded successfully!"
        if 'super_admin' in session.get('roles', []):
            return render_template(
                'admin_student.html',
                active_tab=active_tab,
                error_upload_results=error_upload_results,
                success_upload_results=success_upload_results
            )
        elif 'e-admin' in session.get('roles', []):
            return render_template(
                'e_admin.html',
                active_tab=active_tab,
                error_upload_results=error_upload_results,
                success_upload_results=success_upload_results
            )

    except Exception as e:
        error_upload_results = f"An error occurred: {str(e)}"
        if 'super_admin' in session.get('roles', []):
            return render_template(
                'admin_student.html',
                active_tab=active_tab,
                error_upload_results=error_upload_results,
            )
        elif 'e-admin' in session.get('roles', []):
            return render_template(
                'e_admin.html',
                active_tab=active_tab,
                error_upload_results=error_upload_results,
            )


def extract_semester_from_sheet(sheet_name):
    try:
        sem_number = int(sheet_name.strip().replace('Semester', '').strip())
        if 1 <= sem_number <= 8:
            return sem_number
    except ValueError:
        return None


@app.route('/download', methods=['POST'])
def download_results():
    error_download = request.args.get('error_download')
    success_download = request.args.get('success_download')
    active_tab = 'download_results'

    roll_start_list = request.form.getlist('roll_start_mid[]')
    roll_end_list = request.form.getlist('roll_end_mid[]')
    passed_out_year = request.form.get('passed_out_year')
    sgpa_type = request.form.get('sgpa_type')  # Fetch the SGPA type
    print(roll_start_list)
    print(roll_end_list)
    # Validate inputs
    if not roll_start_list or not roll_end_list or len(roll_start_list) != len(roll_end_list) or roll_start_list > roll_end_list:
        error_download = "Roll number ranges are invalid or mismatched."
        if 'super_admin' in session.get('roles', []):
            return render_template(
                'admin_student.html',
                active_tab=active_tab,
                error_download=error_download,
            )
        elif 'e-admin' in session.get('roles', []):
            return render_template(
                'e_admin.html',
                active_tab=active_tab,
                error_download=error_download,
            )

    def is_valid_student_username(roll_number):
        """Check if roll number is 12 digits and starts with '2456'."""
        return len(roll_number) == 12 and roll_number.startswith('2456')

    invalid_roll_numbers = [
        roll for roll in roll_start_list + roll_end_list if not is_valid_student_username(roll)
    ]
    if invalid_roll_numbers:
        error_download = "Roll numbers entered are incorrect. Please ensure all roll numbers are 12 digits and start with '2456'."
        if 'super_admin' in session.get('roles', []):
            return render_template(
                'admin_student.html',
                active_tab=active_tab,
                error_download=error_download,
            )
        elif 'e-admin' in session.get('roles', []):
            return render_template(
                'e_admin.html',
                active_tab=active_tab,
                error_download=error_download,
            )

    # Create a connection to the database
    connection = pymysql.connect(
        host='localhost',
        user='root',
        password='ammu2007',
        database='user_management'
    )

    try:
        # Dictionary to hold semester data for all roll numbers
        all_semester_data = {f'Semester {i}': {} for i in range(1, 9)}
        data_exists = False  # Flag to check if any data is fetched

        for semester in range(1, 9):
            sgpa_column = (
                f", sc.sem{semester}_actual_sgpa" if sgpa_type == "actual" else
                f", sc.sem{semester}_sgpa" if sgpa_type == "calculated" else
                f", sc.sem{semester}_actual_sgpa, sc.sem{semester}_sgpa"
            )

            for roll_start, roll_end in zip(roll_start_list, roll_end_list):
                query = f"""
                SELECT s.roll_number, s.subject_name, s.subject_code, 
                       s.grade_secured, s.grade_point, s.credits
                       {sgpa_column}
                FROM sem{semester} s
                LEFT JOIN sgpa_cgpa sc ON s.roll_number = sc.roll_number
                WHERE s.roll_number BETWEEN %s AND %s 
                      AND s.passed_out_year = %s
                """
                params = (roll_start, roll_end, passed_out_year)

                with connection.cursor() as cursor:
                    cursor.execute(query, params)
                    subjects = cursor.fetchall()

                if subjects:
                    data_exists = True  # Data is found

                # Process data into roll number-based rows
                for subject in subjects:
                    roll_number = subject[0]
                    subject_name = subject[1]

                    # Initialize row if not exists
                    if roll_number not in all_semester_data[f'Semester {semester}']:
                        all_semester_data[f'Semester {semester}'][roll_number] = {
                        }

                    # Add subject details as columns
                    all_semester_data[f'Semester {semester}'][roll_number].update({
                        f"{subject_name} Grade Secured": subject[3],
                        f"{subject_name} Grade Point": subject[4],
                        f"{subject_name} Credits": subject[5],
                        f"{subject_name} Subject Code": subject[2],
                    })

                    # Add SGPA if available
                    if sgpa_type == "both":
                        all_semester_data[f'Semester {semester}'][roll_number].update({
                            "Actual SGPA": subject[6],
                            "Calculated SGPA": subject[7]
                        })
                    elif sgpa_type == "actual":
                        all_semester_data[f'Semester {semester}'][
                            roll_number]["Actual SGPA"] = subject[6]
                    elif sgpa_type == "calculated":
                        all_semester_data[f'Semester {semester}'][
                            roll_number]["Calculated SGPA"] = subject[6]

        # If no data was found
        if not data_exists:
            error_download = "No data available to download."
            if 'super_admin' in session.get('roles', []):
                return render_template(
                    'admin_student.html',
                    active_tab=active_tab,
                    error_download=error_download,
                )
            elif 'e-admin' in session.get('roles', []):
                return render_template(
                    'e_admin.html',
                    active_tab=active_tab,
                    error_download=error_download,
                )

        # Write to Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            for semester in range(1, 9):
                semester_data = all_semester_data[f'Semester {semester}']
                if semester_data:
                    # Convert to DataFrame
                    df = pd.DataFrame.from_dict(
                        semester_data, orient='index').reset_index()
                    df.rename(columns={'index': 'Roll Number'}, inplace=True)

                    # Reorder columns to place SGPA at the end
                    sgpa_columns = [col for col in df.columns if 'SGPA' in col]
                    other_columns = [
                        col for col in df.columns if col not in sgpa_columns]
                    ordered_columns = other_columns + sgpa_columns
                    df = df[ordered_columns]

                    # Write to sheet
                    df.to_excel(
                        writer, sheet_name=f"Semester {semester}", index=False)

        output.seek(0)
        return send_file(output, as_attachment=True, download_name='results.xlsx',
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    except Exception as e:
        error_download = f"An error occurred: {str(e)}"
        if 'super_admin' in session.get('roles', []):
            return render_template(
                'admin_student.html',
                active_tab=active_tab,
                error_download=error_download,
            )
        elif 'e-admin' in session.get('roles', []):
            return render_template(
                'e_admin.html',
                active_tab=active_tab,
                error_download=error_download,
            )

    finally:
        connection.close()


@app.route('/branch_section_download', methods=['POST'])
def branch_section_download_results():
    error_download = request.args.get('error_download')
    success_download = request.args.get('success_download')
    active_tab = 'download_results'

    branch = request.form.get('branch')
    section = request.form.get('section')
    passed_out_year = request.form.get('passed_out_year')
    sgpa_type = request.form.get('sgpa_type')  # Fetch the SGPA type

    # Validate inputs
    if not branch or not passed_out_year:
        error_download = "Branch and Passed Out Year are required."
        if 'super_admin' in session.get('roles', []):
            return render_template(
                'admin_student.html',
                active_tab=active_tab,
                error_download=error_download,
            )
        elif 'e-admin' in session.get('roles', []):
            return render_template(
                'e_admin.html',
                active_tab=active_tab,
                error_download=error_download,
            )

    # Create a connection to the database
    connection = pymysql.connect(
        host='localhost',
        user='root',
        password='ammu2007',
        database='user_management'
    )

    try:
        # Fetch roll numbers from the profile table based on branch, section, and passed_out_year
        query = """
        SELECT roll_number
        FROM profile
        WHERE Branch = %s
          AND (%s = 'ALL' OR Section = %s)
          AND `Passed out year` = %s
        """
        params = (branch, section, section if section !=
                  'ALL' else '%', passed_out_year)
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            roll_numbers = [row[0] for row in cursor.fetchall()]
        # If no roll numbers are found
        if not roll_numbers:
            error_download = "No students found for the given criteria."
            if 'super_admin' in session.get('roles', []):
                return render_template(
                    'admin_student.html',
                    active_tab=active_tab,
                    error_download=error_download,
                )
            elif 'e-admin' in session.get('roles', []):
                return render_template(
                    'e_admin.html',
                    active_tab=active_tab,
                    error_download=error_download,
                )

        # Dictionary to hold semester data for all roll numbers
        all_semester_data = {f'Semester {i}': {} for i in range(1, 9)}
        data_exists = False

        for semester in range(1, 9):
            sgpa_column = (
                f", sc.sem{semester}_actual_sgpa" if sgpa_type == "actual" else
                f", sc.sem{semester}_sgpa" if sgpa_type == "calculated" else
                f", sc.sem{semester}_actual_sgpa, sc.sem{semester}_sgpa"
            )

            # Query for each roll number and semester
            for roll_number in roll_numbers:
                query = f"""
                SELECT s.roll_number, s.subject_name, s.subject_code, 
                       s.grade_secured, s.grade_point, s.credits
                       {sgpa_column}
                FROM sem{semester} s
                LEFT JOIN sgpa_cgpa sc ON s.roll_number = sc.roll_number
                WHERE s.roll_number = %s
                """
                params = (roll_number,)

                with connection.cursor() as cursor:
                    cursor.execute(query, params)
                    subjects = cursor.fetchall()

                if subjects:
                    data_exists = True  # Data is found

                # Process data into roll number-based rows
                for subject in subjects:
                    roll_number = subject[0]
                    subject_name = subject[1]

                    # Initialize row if not exists
                    if roll_number not in all_semester_data[f'Semester {semester}']:
                        all_semester_data[f'Semester {semester}'][roll_number] = {
                        }

                    # Add subject details as columns
                    all_semester_data[f'Semester {semester}'][roll_number].update({
                        f"{subject_name} Grade Secured": subject[3],
                        f"{subject_name} Grade Point": subject[4],
                        f"{subject_name} Credits": subject[5],
                        f"{subject_name} Subject Code": subject[2],
                    })

                    # Add SGPA if available
                    if sgpa_type == "both":
                        all_semester_data[f'Semester {semester}'][roll_number].update({
                            "Actual SGPA": subject[6],
                            "Calculated SGPA": subject[7]
                        })
                    elif sgpa_type == "actual":
                        all_semester_data[f'Semester {semester}'][
                            roll_number]["Actual SGPA"] = subject[6]
                    elif sgpa_type == "calculated":
                        all_semester_data[f'Semester {semester}'][
                            roll_number]["Calculated SGPA"] = subject[6]

        # If no data was found
        if not data_exists:
            error_download = "No data available to download."
            if 'super_admin' in session.get('roles', []):
                return render_template(
                    'admin_student.html',
                    active_tab=active_tab,
                    error_download=error_download,
                )
            elif 'e-admin' in session.get('roles', []):
                return render_template(
                    'e_admin.html',
                    active_tab=active_tab,
                    error_download=error_download,
                )

        # Write to Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            for semester in range(1, 9):
                semester_data = all_semester_data[f'Semester {semester}']
                if semester_data:
                    # Convert to DataFrame
                    df = pd.DataFrame.from_dict(
                        semester_data, orient='index').reset_index()
                    df.rename(columns={'index': 'Roll Number'}, inplace=True)

                    # Reorder columns to place SGPA at the end
                    sgpa_columns = [col for col in df.columns if 'SGPA' in col]
                    other_columns = [
                        col for col in df.columns if col not in sgpa_columns]
                    ordered_columns = other_columns + sgpa_columns
                    df = df[ordered_columns]

                    # Write to sheet
                    df.to_excel(
                        writer, sheet_name=f"Semester {semester}", index=False)

        output.seek(0)
        return send_file(output, as_attachment=True, download_name='results.xlsx',
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    except Exception as e:
        error_download = f"An error occurred: {str(e)}"
        if 'super_admin' in session.get('roles', []):
            return render_template(
                'admin_student.html',
                active_tab=active_tab,
                error_download=error_download,
            )
        elif 'e-admin' in session.get('roles', []):
            return render_template(
                'e_admin.html',
                active_tab=active_tab,
                error_download=error_download,
            )

    finally:
        connection.close()


def update_active_years_table():
    """
    Create or update the active_years table with the 4 highest passed-out years from the profile table.
    """
    try:
        connection = get_db_connection()
        cursor = connection.cursor(pymysql.cursors.DictCursor)

        # Create the active_years table if it doesn't exist
        create_table_query = """
        CREATE TABLE IF NOT EXISTS active_years (
            year VARCHAR(255) UNIQUE
        )
        """
        cursor.execute(create_table_query)

        # Fetch the 4 highest passed-out years
        fetch_years_query = """
        SELECT DISTINCT `Passed out year`
        FROM profile
        WHERE `Passed out year` IS NOT NULL
        ORDER BY CAST(`Passed out year` AS UNSIGNED) DESC
        LIMIT 4
        """
        cursor.execute(fetch_years_query)
        highest_years = cursor.fetchall()
        print("Fetched Active Years Data:", highest_years)

        # Clear the active_years table
        cursor.execute("TRUNCATE TABLE active_years")

        # Insert the 4 highest years into the active_years table
        insert_query = "INSERT INTO active_years (year) VALUES (%s)"
        for year in highest_years:
            cursor.execute(insert_query, (year["Passed out year"],))

        connection.commit()
        cursor.close()
        connection.close()
    except Exception as e:
        print(f"Error updating active_years table:  {traceback.format_exc()}")


def update_branch_sections_table():
    """
    Create or update the branch_sections table based on data from the profile table.
    """
    try:
        # Connect to MySQL database
        connection = get_db_connection()
        cursor = connection.cursor(pymysql.cursors.DictCursor)

        # Create the branch_sections table if it doesn't exist
        create_table_query = """
        CREATE TABLE IF NOT EXISTS branch_sections (
            branch VARCHAR(255) PRIMARY KEY,
            sections JSON
        )
        """
        cursor.execute(create_table_query)

        # Fetch branch and sections from the profile table
        fetch_query = """
        SELECT Branch, GROUP_CONCAT(DISTINCT Section ORDER BY Section) AS Sections
        FROM profile
        WHERE Branch IS NOT NULL AND Section IS NOT NULL
        GROUP BY Branch
        """
        cursor.execute(fetch_query)
        data = cursor.fetchall()

        # Insert or update data into branch_sections table
        for row in data:
            branch = row["Branch"]
            sections = row["Sections"]

            # Convert sections to JSON array
            sections_json = '["' + sections.replace(',', '", "') + '"]'
            insert_update_query = """
            INSERT INTO branch_sections (branch, sections)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE sections = VALUES(sections)
            """
            cursor.execute(insert_update_query, (branch, sections_json))

        connection.commit()
        cursor.close()
        connection.close()
        print("Branch sections updated successfully!")
    except Exception as e:
        print(
            f"Error updating branch_sections table:  {traceback.format_exc()}")


def update_year_branch_section_table():
    """
    Create or update the year_branch_section table with the active years and their associated branches and sections.
    """
    try:
        connection = get_db_connection()
        cursor = connection.cursor(pymysql.cursors.DictCursor)

        # Create the year_branch_section table if it doesn't exist
        create_table_query = """
        CREATE TABLE IF NOT EXISTS year_branch_section (
            active_year VARCHAR(255) PRIMARY KEY,
            branch_section JSON
        )
        """
        cursor.execute(create_table_query)

        # Fetch the 4 highest passed-out years
        fetch_years_query = """
        SELECT DISTINCT `Passed out year`
        FROM profile
        WHERE `Passed out year` IS NOT NULL
        ORDER BY CAST(`Passed out year` AS UNSIGNED) DESC
        LIMIT 4
        """
        cursor.execute(fetch_years_query)
        active_years = cursor.fetchall()

        # Prepare the data for each active year
        for year in active_years:
            active_year = year["Passed out year"]

            # Fetch branches and their sections for the current active year
            fetch_branches_query = """
            SELECT Branch, GROUP_CONCAT(DISTINCT Section ORDER BY Section) AS Sections
            FROM profile
            WHERE `Passed out year` = %s AND Branch IS NOT NULL AND Section IS NOT NULL
            GROUP BY Branch
            """
            cursor.execute(fetch_branches_query, (active_year,))
            branch_data = cursor.fetchall()

            # Convert branch and sections data to JSON format
            branch_section_json = {}
            for row in branch_data:
                branch = row["Branch"]
                sections = row["Sections"]
                branch_section_json[branch] = sections.split(',')

            # Insert or update the year_branch_section table
            insert_update_query = """
            INSERT INTO year_branch_section (active_year, branch_section)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE branch_section = VALUES(branch_section)
            """
            cursor.execute(insert_update_query, (active_year,
                           json.dumps(branch_section_json)))

        connection.commit()
        cursor.close()
        connection.close()
        print("Year branch section updated successfully!")
    except Exception as e:
        print(
            f"Error updating year_branch_section table: {traceback.format_exc()}")


@app.route('/upload_profile', methods=['POST'])
def upload_file():
    active_tab = 'upload_profile'  # Set the active tab to 'upload_profile'
    error_upload_profile = None
    success_upload_profile = None

    if 'file' not in request.files:
        error_upload_profile = "No file part"
        return render_template('admin_student.html', active_tab=active_tab, error_upload_profile=error_upload_profile)

    file = request.files['file']

    if file.filename == '':
        error_upload_profile = "No selected file"
        return render_template('admin_student.html', active_tab=active_tab, error_upload_profile=error_upload_profile)

    # Process the Excel file directly without saving it
    result = process_excel(file)
    if "successfully" not in result:
        error_upload_profile = result  # Return the error if any
        return render_template('admin_student.html', active_tab=active_tab, error_upload_profile=error_upload_profile)

    # Update database tables
    update_branch_sections_table()
    update_active_years_table()
    update_year_branch_section_table()

    # After successfully inserting data into the profile table, create the sgpa_cgpa table
    create_sgpa_cgpa_table()

    success_upload_profile = "File uploaded and processed successfully!"

    return render_template('admin_student.html', active_tab=active_tab, success_upload_profile=success_upload_profile)

# repeated code


def process_excel(file):
    # Read the Excel file using pandas directly from the file object
    try:
        df = pd.read_excel(file)
    except Exception as e:
        return f"Error reading the Excel file: {str(e)}"

    # Ensure there are no duplicate column names
    if df.columns.duplicated().any():
        return "Error: Duplicate column names found. Please upload a valid Excel file."

    # Ensure there are no duplicate rows based on 'roll_number'
    df = df.drop_duplicates(subset=['roll_number'])

    # Get column names from the Excel file
    columns = df.columns

    # Escape column names to handle special characters
    columns_escaped = [f"`{col}`" for col in columns]

    # Connect to MySQL database
    connection = get_db_connection()
    cursor = connection.cursor()

    # Check if profile table exists, if not, create it
    cursor.execute("SHOW TABLES LIKE 'profile'")
    result = cursor.fetchone()
    if not result:
        create_table_query = f"""
        CREATE TABLE profile (
            roll_number VARCHAR(255) PRIMARY KEY
        )
        """
        cursor.execute(create_table_query)

    # Check for new columns in the profile table and add them if they don't exist
    for column in columns:
        cursor.execute(f"SHOW COLUMNS FROM profile LIKE '{column}'")
        result = cursor.fetchall()  # Consume the result set
        if not result:
            cursor.execute(
                f"ALTER TABLE profile ADD COLUMN `{column}` VARCHAR(255) DEFAULT NULL")

    # Insert data into the table, ensuring no duplicate 'roll_number'
    for _, row in df.iterrows():
        # Prepare the SQL INSERT statement
        insert_query = f"""
        INSERT INTO profile ({', '.join(columns_escaped)}) 
        VALUES ({', '.join(['%s'] * len(columns))})
        ON DUPLICATE KEY UPDATE {', '.join([f'{col}=VALUES({col})' for col in columns_escaped])}
        """
        # Prepare the row values
        # Replace NaN with None
        row_values = [str(val) if pd.notna(val) else None for val in row]
        cursor.execute(insert_query, row_values)

    connection.commit()
    cursor.close()
    connection.close()

    return "Data inserted successfully!"


def create_sgpa_cgpa_table():
    # Prepare the SQL CREATE TABLE statement for sgpa_cgpa table
    create_sgpa_cgpa_query = """
    CREATE TABLE IF NOT EXISTS sgpa_cgpa (
        id INT AUTO_INCREMENT PRIMARY KEY,
        roll_number VARCHAR(255) UNIQUE,
        sem1_sgpa DECIMAL(4, 2),
        sem2_sgpa DECIMAL(4, 2),
        sem3_sgpa DECIMAL(4, 2),
        sem4_sgpa DECIMAL(4, 2),
        sem5_sgpa DECIMAL(4, 2),
        sem6_sgpa DECIMAL(4, 2),
        sem7_sgpa DECIMAL(4, 2),
        sem8_sgpa DECIMAL(4, 2),
        sem1_actual_sgpa VARCHAR(20),
        sem2_actual_sgpa VARCHAR(20),
        sem3_actual_sgpa VARCHAR(20),
        sem4_actual_sgpa VARCHAR(20),
        sem5_actual_sgpa VARCHAR(20),
        sem6_actual_sgpa VARCHAR(20),
        sem7_actual_sgpa VARCHAR(20),
        sem8_actual_sgpa VARCHAR(20),
        cgpa DECIMAL(4, 2),
        total_credits FLOAT,
        no_of_backlogs INT,
        Status VARCHAR(20) DEFAULT 'Active'
    )
    """

    # Connect to MySQL database
    connection = get_db_connection()
    cursor = connection.cursor()

    # Create the sgpa_cgpa table
    cursor.execute(create_sgpa_cgpa_query)

    connection.commit()
    cursor.close()
    connection.close()

    return "Data inserted successfully!"


@app.route('/get_profile_columns', methods=['GET'])
def get_profile_columns():
    try:
        conn = pymysql.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM profile LIMIT 0")
        columns = [column[0] for column in cursor.description]
        conn.close()
        return jsonify({'columns': columns})
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/get_data', methods=['GET'])
def get_data():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch subject data
    subject_query = "SELECT subject_code, subject_name FROM subject"
    cursor.execute(subject_query)
    subject_rows = cursor.fetchall()

    # Create a mapping of subject codes to names
    subject_mapping = {row['subject_code']: row['subject_name']
                       for row in subject_rows}

    # Fetch assessment data
    query = "SELECT assessment_data FROM faculty_assessment"
    cursor.execute(query)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    subjects = set()
    year_branch_section = {}

    # Process data
    for row in rows:
        assessment_data = json.loads(row['assessment_data'])
        for subject_code, year_data in assessment_data.items():
            subjects.add(subject_code)
            for year, sections in year_data.items():
                if subject_code not in year_branch_section:
                    year_branch_section[subject_code] = {}
                if year not in year_branch_section[subject_code]:
                    year_branch_section[subject_code][year] = set()
                year_branch_section[subject_code][year].update(sections)

    # Format data for dropdown
    subjects = sorted(list(subjects))
    formatted_data = {
        "subjects": [{"code": code, "name": subject_mapping.get(code, code)} for code in subjects],
        "year_branch_section": {k: {yr: list(sec) for yr, sec in v.items()} for k, v in year_branch_section.items()}
    }
    return jsonify(formatted_data)


@app.route('/admin_academic_result')
def admin_academic_result():
    roles = session.get('roles', [])
    roll_number = session.get('roll_number')
    if not roll_number:
        return redirect(url_for('index'))

    all_sem_results = {}
    sgpa_data = fetch_sgpa(roll_number)
    internal_marks_data = {}

    if sgpa_data is not None:
        print(f"SGPA Data Retrieved: {sgpa_data}")
    else:
        print("No SGPA data found.")

    for sem in range(1, 9):
        sem_name = f"sem{sem}"
        all_sem_results[sem_name] = fetch_results(roll_number, sem_name)

        # Fetch internal marks for the current semester
        internal_marks = fetch_internal_marks(roll_number, sem)
        if internal_marks:
            internal_marks_data[sem_name] = internal_marks
    db = get_db_connection()
    cursor = db.cursor()

    query = """
        SELECT Branch, roll_number,`Admitted year`,`Passed out year`, `STUDENT NAME`, `FATHER NAME`, `DATE OF BIRTH (MM/DD/YYYY)`, Sex, 
               `Joined By`, `Rank`, `SSC Marks`, `Inter/ Diploma Marks`
        FROM profile WHERE roll_number = %s
    """
    cursor.execute(query, (roll_number,))
    student = cursor.fetchone()
    # Fetch CGPA from sgpa_cgpa table
    cgpa_query = """
        SELECT cgpa FROM sgpa_cgpa WHERE roll_number = %s
    """
    cursor.execute(cgpa_query, (roll_number,))
    cgpa_result = cursor.fetchone()

    cursor.close()
    db.close()

    cgpa = cgpa_result['cgpa'] if cgpa_result else None
    flattened_internal_marks_data = {
        k: v for k, v in internal_marks_data.items() if v}
    if not student:
        return render_template('admin_academic_result.html', error="No student found.", roles=roles)

    return render_template('admin_academic_result.html',
                           all_sem_results=all_sem_results,
                           sgpa_data=sgpa_data,
                           internal_marks_data=flattened_internal_marks_data,
                           student=student,
                           roll_number=roll_number,
                           cgpa=cgpa, roles=roles)


@app.route('/admin_edit_academic_results', methods=['GET', 'POST'])
def admin_edit_academic_results():
    roll_number = session.get('roll_number')
    if not roll_number:
        return redirect(url_for('index'))

    db = get_db_connection()
    cursor = db.cursor()

    all_sem_results = {}

    if request.method == 'POST':
        # Get the profile data
        profile_data = {
            'Branch': request.form.get('Branch')
        }

        # Check if Passed Out Year is provided
        passed_out_year = request.form.get('Passed Out Year')
        if passed_out_year:
            profile_data['Passed Out Year'] = passed_out_year
        else:
            # or some default value if needed
            profile_data['Passed Out Year'] = None

        status = request.form.get('Status')

        if status == 'Detained' and passed_out_year:
            # If the status is Detained, and Passed Out Year is provided, update it
            # Debugging line
            print(f"Updating Passed Out Year to: {passed_out_year}")
            profile_data['Passed Out Year'] = passed_out_year
        elif status == 'Drop':
            # If status is Drop, don't change the Passed Out Year
            cursor.execute(
                "SELECT `Passed Out Year` FROM profile WHERE roll_number = %s", (roll_number,))
            result = cursor.fetchone()
            if result and result['Passed Out Year']:
                # Keep the existing Passed Out Year if status is Drop
                profile_data['Passed Out Year'] = result['Passed Out Year']

        # Update the profile with Passed Out Year
        profile_update_query = """
            UPDATE profile SET 
            `Branch` = %s, 
            `Passed Out Year` = %s
            WHERE roll_number = %s
        """
        profile_values = tuple(profile_data.values()) + (roll_number,)
        cursor.execute(profile_update_query, profile_values)

        # Update the Passed Out Year in internal_marks as well
        update_internal_marks_query = """
            UPDATE internal_marks
            SET `passed_out_year` = %s
            WHERE roll_number = %s
        """
        cursor.execute(update_internal_marks_query,
                       (profile_data['Passed Out Year'], roll_number))

        # Update the Status in sgpa_cgpa table
        status_update_query = """
            UPDATE sgpa_cgpa SET 
            `Status` = %s 
            WHERE roll_number = %s
        """
        cursor.execute(status_update_query, (status, roll_number))

        db.commit()

        if cursor.rowcount > 0:
            flash("Academic profile updated successfully!")
        else:
            flash("No changes were made to the academic profile.")

        return redirect(url_for('admin_edit_academic_results'))

    # Fetch current academic profile details
    cursor.execute(
        "SELECT * FROM profile WHERE roll_number = %s", (roll_number,))
    academic_profile_details = cursor.fetchone()

    # Fetch the current Status from sgpa_cgpa table
    cursor.execute(
        "SELECT Status FROM sgpa_cgpa WHERE roll_number = %s", (roll_number,))
    status_data = cursor.fetchone()

    cursor.close()
    db.close()

    return render_template(
        'admin_edit_academic_results.html',
        academic_profile=academic_profile_details,
        sgpa_data=status_data,  # Pass the status data to the template
        all_sem_results=all_sem_results
    )


@app.route('/admin_edit_profile', methods=['GET', 'POST'])
def admin_edit_profile():
    roll_number = session.get('roll_number')
    if not roll_number:
        return redirect(url_for('index'))

    db = get_db_connection()
    cursor = db.cursor()

    if request.method == 'POST':
        updated_data = request.form.to_dict()  # Get all form data as a dictionary

        # Ensure username is included in updated_data
        if 'roll_number' not in updated_data:
            updated_data['roll_number'] = roll_number

        # Build the dynamic update query
        set_clause = ", ".join(
            [f"`{col}` = %s" for col in updated_data.keys() if col != 'roll_number'])
        values = [value for key, value in updated_data.items() if key !=
                  'roll_number'] + [roll_number]

        update_query = f"UPDATE profile SET {set_clause} WHERE roll_number = %s"

        try:
            cursor.execute(update_query, values)
            db.commit()

            if cursor.rowcount == 0:
                flash("No changes were made to the profile.")
            else:
                flash("Profile updated successfully!")
                return redirect(url_for('admin_profile'))

        except Exception as e:
            db.rollback()
            flash(f"An error occurred while updating the profile: {str(e)}")

    query = "SELECT * FROM profile WHERE roll_number = %s"
    cursor.execute(query, (roll_number,))
    profile_details = cursor.fetchone()

    cursor.close()
    db.close()

    return render_template('admin_edit_profile.html', profile=profile_details)


@app.route('/admin_profile', methods=['GET', 'POST'])
def admin_profile():
    # Retrieve roles from the session
    roles = session.get('roles', [])

    # Initialize variables for error and success messages
    error_admin_profile = request.args.get('error')
    success_admin_profile = request.args.get('success')
    active_tab = request.args.get('active_tab', 'admin_profile')

    if request.method == 'POST':
        # Extract roll_number from the form and store it in the session
        roll_number = request.form.get('roll_number')
        session['roll_number'] = roll_number  # Save it to the session
    else:
        # Retrieve roll_number from session
        roll_number = session.get('roll_number')

    def is_valid_student_username(username):
        # Validate that the roll number is 12 digits and starts with '2456'
        return len(username) == 12 and username.startswith('2456')

    # Redirect if roll_number is not present
    if not roll_number:
        return redirect(url_for('index'))

    # Validate roll number format
    if not is_valid_student_username(roll_number):
        error_admin_profile = "Roll number must be 12 digits and start with 2456."
        if 'super_admin' in session.get('roles', []):
            return render_template('admin_student.html', error_admin_profile=error_admin_profile, active_tab=active_tab, roles=roles)
        elif 'hod' in session.get('roles', []):
            return render_template('hod.html', error_admin_profile=error_admin_profile, active_tab=active_tab, roles=roles)

    # Connect to the database and check if the user exists
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM profile WHERE roll_number = %s", (roll_number,))
        existing_user = cursor.fetchone()

        if not existing_user:
            error_admin_profile = f"User {roll_number} does not exist."
            if 'super_admin' in session.get('roles', []):
                return render_template('admin_student.html', error_admin_profile=error_admin_profile, active_tab=active_tab, roles=roles)
            elif 'hod' in session.get('roles', []):
                return render_template('hod.html', error_admin_profile=error_admin_profile, active_tab=active_tab, roles=roles)

        # Query to get profile details
        query = "SELECT * FROM profile WHERE roll_number = %s"
        cursor.execute(query, (roll_number,))
        profile_details = cursor.fetchone()

    except Exception as e:
        error_admin_profile = "Database error:", e
        if 'super_admin' in session.get('roles', []):
            return render_template('admin_student.html', error_admin_profile=error_admin_profile, active_tab=active_tab, roles=roles)
        elif 'hod' in session.get('roles', []):
            return render_template('hod.html', error_admin_profile=error_admin_profile, active_tab=active_tab, roles=roles)
    finally:
        # Close database connection
        cursor.close()
        conn.close()

    if profile_details:
        # Mask sensitive information (Aadhar and PAN numbers)
        aadhar_number = str(profile_details.get('AADHAAR CARD NO', ''))
        pan_number = str(profile_details.get('PAN Card No', ''))

        if aadhar_number:
            profile_details['AADHAAR CARD NO'] = '****' + aadhar_number[-4:]

        if pan_number:
            profile_details['PAN Card No'] = '****' + pan_number[-4:]

    return render_template('admin_profile.html', profile_details=profile_details, roles=roles)


@app.route('/download_mid_marks', methods=['POST'])
def download_mid_marks():
    error_download_mid_marks = request.args.get('error_download_mid_marks')
    success_download_mid_marks = request.args.get('success_download_mid_marks')
    active_tab = 'download_mid_marks'

    # Gather input data
    roll_start_ranges = request.form.getlist('roll_start_mid[]')
    roll_end_ranges = request.form.getlist('roll_end_mid[]')
    passed_out_year = request.form['passed_out_year']
    selected_columns = request.form.getlist('columns[]')
    # 'general' or 'subject_wise'
    download_type = request.form['download_type']

    def is_valid_student_username(roll_number):
        """Check if roll number is 12 digits and starts with '2456'."""
        return len(str(roll_number)) == 12 and str(roll_number).startswith('2456')

    # Validate roll number ranges and roll number format
    errors = []
    for start, end in zip(roll_start_ranges, roll_end_ranges):
        if not is_valid_student_username(start) or not is_valid_student_username(end):
            errors.append(
                f"Invalid roll number format: {start} or {end}. Roll numbers must be 12 digits and start with '2456'.")

    if not roll_start_ranges or not roll_end_ranges or len(roll_start_ranges) != len(roll_end_ranges) or roll_start_ranges > roll_end_ranges:
        errors.append("Invalid roll number ranges provided.")

    if errors:
        if 'e-admin' in session.get('roles', []):
            return render_template(
                'e_admin.html',
                active_tab=active_tab,
                error_download_mid_marks=errors,
            )
        elif 'hod' in session.get('roles', []):
            return render_template(
                'hod.html',
                active_tab=active_tab,
                error_download_mid_marks=errors,
            )

    try:
        # Connect to the database
        conn = pymysql.connect(**db_config)
        cursor = conn.cursor()

        # Prepare query to fetch data
        roll_number_conditions = []
        for start, end in zip(roll_start_ranges, roll_end_ranges):
            roll_number_conditions.append(
                f"(roll_number BETWEEN {start} AND {end})")
        roll_number_filter = " OR ".join(roll_number_conditions)

        query = f"""
            SELECT roll_number, subject_name, cie1, cie2, assignment, avg, total, passed_out_year
            FROM internal_marks
            WHERE passed_out_year = %s AND ({roll_number_filter})
        """
        cursor.execute(query, (passed_out_year,))
        data = cursor.fetchall()

        if not data:
            errors.append("No records found for the given criteria.")
            if 'e-admin' in session.get('roles', []):
                return render_template(
                    'e_admin.html',
                    active_tab=active_tab,
                    error_download_mid_marks=errors,
                )
            elif 'hod' in session.get('roles', []):
                return render_template(
                    'hod.html',
                    active_tab=active_tab,
                    error_download_mid_marks=errors,
                )

        # Get student names from the profile table
        student_query = f"""
    SELECT roll_number, `STUDENT NAME`
    FROM profile
    WHERE roll_number IN ({','.join([str(row[0]) for row in data])})
"""

        cursor.execute(student_query)
        student_names = {row[0]: row[1] for row in cursor.fetchall()}

        # Process data for Excel
        df = pd.DataFrame(data, columns=['roll_number', 'subject_name',
                          'cie1', 'cie2', 'assignment', 'avg', 'total', 'passed_out_year'])

        # If Subject Wise is selected, generate separate sheets for CIE1 and CIE2
        if download_type == 'subject_wise':
            # Pivot tables for CIE1 and CIE2 marks
            cie1_data = df[['roll_number', 'subject_name', 'cie1']].pivot_table(
                index='roll_number', columns='subject_name', values='cie1', aggfunc='first')
            cie2_data = df[['roll_number', 'subject_name', 'cie2']].pivot_table(
                index='roll_number', columns='subject_name', values='cie2', aggfunc='first')

            # If 'name' is selected in columns, add student names
            if 'name' in selected_columns:
                # Add student names to subject-wise data (based on roll number)
                cie1_data['Name'] = cie1_data.index.map(student_names)
                cie2_data['Name'] = cie2_data.index.map(student_names)

            # Reorder columns to have 'Name' next to 'Roll Number'
            cie1_data = cie1_data[[
                'Name'] + [col for col in cie1_data.columns if col != 'Name']]
            cie2_data = cie2_data[[
                'Name'] + [col for col in cie2_data.columns if col != 'Name']]

            # Create a new Excel writer
            with pd.ExcelWriter('subject_wise_mid_marks.xlsx') as writer:
                # Save CIE1 and CIE2 data to separate sheets
                cie1_data.to_excel(writer, sheet_name='CIE1')
                cie2_data.to_excel(writer, sheet_name='CIE2')

            # Send the file for download
            return send_file('subject_wise_mid_marks.xlsx', as_attachment=True)

        # Otherwise, handle General Download (with checkboxes)
        excel_data = []
        for roll in df['roll_number'].unique():
            subject_headers = df['subject_name'].unique()

            student_data = df[df['roll_number'] == roll]
            row = {'Roll Number': roll}
            total_marks = 0

            if 'name' in selected_columns:
                row['Name'] = student_names.get(roll, 'N/A')
            for column in selected_columns:
                if column == 'subject_name':
                    for subject in subject_headers:
                        if 'subject_name' in selected_columns:
                            subject_data = student_data[student_data['subject_name'] == subject]
                            if not subject_data.empty:
                                total_for_subject = subject_data['cie1'] + \
                                    subject_data['cie2'] + \
                                    subject_data['assignment']
                                row[subject] = total_for_subject.sum()
                                total_marks += total_for_subject.sum()
                            else:
                                row[subject] = 0

            if 'cie1' in selected_columns:
                row['CIE1'] = student_data['cie1'].sum()

            if 'cie2' in selected_columns:
                row['CIE2'] = student_data['cie2'].sum()

            if 'avg' in selected_columns:
                row['Average'] = student_data['avg'].iloc[0]

            if 'assignment' in selected_columns:
                row['Assignment'] = student_data['assignment'].sum()

            if 'total' in selected_columns:
                row['Total'] = student_data['total'].sum()

            if 'percentage' in selected_columns:
                total_marks = student_data['cie1'].sum(
                ) + student_data['cie2'].sum() + student_data['assignment'].sum()
                max_possible_marks = len(student_data) * 20
                row['Percentage'] = (
                    total_marks / max_possible_marks) * 100 if max_possible_marks > 0 else 0

            excel_data.append(row)

        result_df = pd.DataFrame(excel_data)
        file_path = 'general_mid_marks.xlsx'
        result_df.to_excel(file_path, index=False)

        # Cleanup DB connection
        cursor.close()
        conn.close()

        # Send file for download
        return send_file(file_path, as_attachment=True)

    except Exception as e:
        errors.append(f"An error occurred: {str(e)}")
        if 'e-admin' in session.get('roles', []):
            return render_template(
                'e_admin.html',
                active_tab=active_tab,
                error_download_mid_marks=errors,
            )
        elif 'hod' in session.get('roles', []):
            return render_template(
                'hod.html',
                active_tab=active_tab,
                error_download_mid_marks=errors,
            )


@app.route('/download_mid_marks_branch_section', methods=['POST'])
def download_mid_marks_branch_section():
    error_download_mid_marks = request.args.get('error_download_mid_marks')
    success_download_mid_marks = request.args.get('success_download_mid_marks')
    active_tab = 'download_mid_marks'

    # Gather input data
    branch = request.form.get('branch')
    section = request.form.get('section')
    passed_out_year = request.form['passed_out_year']
    selected_columns = request.form.getlist('columns[]')
    download_type = request.form['download_type']

    # Validate branch and section selection
    errors = []
    if not branch or not section:
        errors.append("Branch and Section must be selected.")

    if errors:
        if 'e-admin' in session.get('roles', []):
            return render_template(
                'e_admin.html',
                active_tab=active_tab,
                error_download_mid_marks=errors,
            )
        elif 'hod' in session.get('roles', []):
            return render_template(
                'hod.html',
                active_tab=active_tab,
                error_download_mid_marks=errors,
            )

    try:
        # Connect to the database
        conn = pymysql.connect(**db_config)
        cursor = conn.cursor()

        # Query to fetch roll numbers based on branch and section
        query = """
            SELECT roll_number
            FROM profile
            WHERE Branch = %s
              AND (%s = 'ALL' OR Section = %s)
              AND `Passed out year` = %s
        """
        params = (branch, section, section if section !=
                  'ALL' else '%', passed_out_year)
        cursor.execute(query, params)
        roll_numbers = [row['roll_number'] for row in cursor.fetchall()]

        if not roll_numbers:
            errors.append("No records found for the given criteria.")
            if 'e-admin' in session.get('roles', []):
                return render_template(
                    'e_admin.html',
                    active_tab=active_tab,
                    error_download_mid_marks=errors,
                )
            elif 'hod' in session.get('roles', []):
                return render_template(
                    'hod.html',
                    active_tab=active_tab,
                    error_download_mid_marks=errors,
                )

        # Prepare query to fetch data for the selected roll numbers
        query = f"""
            SELECT roll_number, subject_name, cie1, cie2, assignment, avg, total, passed_out_year
            FROM internal_marks
            WHERE passed_out_year = %s AND roll_number IN ({','.join([str(roll) for roll in roll_numbers])})
        """
        cursor.execute(query, (passed_out_year,))
        data = cursor.fetchall()

        if not data:
            errors.append("No records found for the selected roll numbers.")
            if 'e-admin' in session.get('roles', []):
                return render_template(
                    'e_admin.html',
                    active_tab=active_tab,
                    error_download_mid_marks=errors,
                )
            elif 'hod' in session.get('roles', []):
                return render_template(
                    'hod.html',
                    active_tab=active_tab,
                    error_download_mid_marks=errors,
                )

        # Get student names from the profile table
        student_query = f"""
            SELECT roll_number, `STUDENT NAME`
            FROM profile
            WHERE roll_number IN ({','.join([str(roll) for roll in roll_numbers])})
        """
        cursor.execute(student_query)
        student_names = {row['roll_number']: row['STUDENT NAME']
                         for row in cursor.fetchall()}

        # Process data for Excel
        df = pd.DataFrame(data)

        # If Subject Wise is selected, generate separate sheets for CIE1 and CIE2
        if download_type == 'subject_wise':
            # Pivot tables for CIE1 and CIE2 marks
            cie1_data = df[['roll_number', 'subject_name', 'cie1']].pivot_table(
                index='roll_number', columns='subject_name', values='cie1', aggfunc='first')
            cie2_data = df[['roll_number', 'subject_name', 'cie2']].pivot_table(
                index='roll_number', columns='subject_name', values='cie2', aggfunc='first')

            # If 'name' is selected in columns, add student names
            if 'name' in selected_columns:
                # Add student names to subject-wise data (based on roll number)
                cie1_data['Name'] = cie1_data.index.map(student_names)
                cie2_data['Name'] = cie2_data.index.map(student_names)

            # Reorder columns to have 'Name' next to 'Roll Number'
            cie1_data = cie1_data[[
                'Name'] + [col for col in cie1_data.columns if col != 'Name']]
            cie2_data = cie2_data[[
                'Name'] + [col for col in cie2_data.columns if col != 'Name']]

            # Create a new Excel writer
            with pd.ExcelWriter('subject_wise_mid_marks.xlsx') as writer:
                # Save CIE1 and CIE2 data to separate sheets
                cie1_data.to_excel(writer, sheet_name='CIE1')
                cie2_data.to_excel(writer, sheet_name='CIE2')

            # Send the file for download
            return send_file('subject_wise_mid_marks.xlsx', as_attachment=True)

        # Otherwise, handle General Download (with checkboxes)
        excel_data = []
        for roll in df['roll_number'].unique():
            subject_headers = df['subject_name'].unique()

            student_data = df[df['roll_number'] == roll]
            row = {'Roll Number': roll}
            total_marks = 0

            if 'name' in selected_columns:
                row['Name'] = student_names.get(roll, 'N/A')
            for column in selected_columns:
                if column == 'subject_name':
                    for subject in subject_headers:
                        if 'subject_name' in selected_columns:
                            subject_data = student_data[student_data['subject_name'] == subject]
                            if not subject_data.empty:
                                total_for_subject = subject_data['cie1'] + \
                                    subject_data['cie2'] + \
                                    subject_data['assignment']
                                row[subject] = total_for_subject.sum()
                                total_marks += total_for_subject.sum()
                            else:
                                row[subject] = 0

            if 'cie1' in selected_columns:
                row['CIE1'] = student_data['cie1'].sum()

            if 'cie2' in selected_columns:
                row['CIE2'] = student_data['cie2'].sum()

            if 'avg' in selected_columns:
                row['Average'] = student_data['avg'].iloc[0]

            if 'assignment' in selected_columns:
                row['Assignment'] = student_data['assignment'].sum()

            if 'total' in selected_columns:
                row['Total'] = student_data['total'].sum()

            if 'percentage' in selected_columns:
                total_marks = student_data['cie1'].sum(
                ) + student_data['cie2'].sum() + student_data['assignment'].sum()
                max_possible_marks = len(student_data) * 20
                row['Percentage'] = (
                    total_marks / max_possible_marks) * 100 if max_possible_marks > 0 else 0

            excel_data.append(row)

        result_df = pd.DataFrame(excel_data)
        file_path = 'general_mid_marks.xlsx'
        result_df.to_excel(file_path, index=False)

        # Cleanup DB connection
        cursor.close()
        conn.close()

        # Send file for download
        return send_file(file_path, as_attachment=True)

    except Exception as e:
        errors.append(f"An error occurred: {str(e)}")
        if 'e-admin' in session.get('roles', []):
            return render_template(
                'e_admin.html',
                active_tab=active_tab,
                error_download_mid_marks=errors,
            )
        elif 'hod' in session.get('roles', []):
            return render_template(
                'hod.html',
                active_tab=active_tab,
                error_download_mid_marks=errors,
            )


@app.route('/view_mid_marks', methods=['POST'])
def view_mid_marks():
    error_download_mid_marks = request.args.get('error_download_mid_marks')
    active_tab = 'view_mid_marks'

    # Gather input data from the form
    roll_start_ranges = request.form.getlist('roll_start_mid[]')
    roll_end_ranges = request.form.getlist('roll_end_mid[]')
    passed_out_year = request.form['passed_out_year']
    selected_columns = request.form.getlist('columns[]')
    download_type = request.form.get(
        'download_type')  # Get the selected view type
    if roll_start_ranges > roll_end_ranges:
        return render_template(
            'hod.html',
            active_tab=active_tab,
            error_download_mid_marks='Invalid roll range. Start roll cannot be greater than end roll.'
        ), 400

    def is_valid_student_username(roll_number):
        """Check if roll number is 12 digits and starts with '2456'."""
        return len(str(roll_number)) == 12 and str(roll_number).startswith('2456')

    # Validate input
    errors = []
    for start, end in zip(roll_start_ranges, roll_end_ranges):
        if not is_valid_student_username(start) or not is_valid_student_username(end):
            errors.append(
                f"Invalid roll number format: {start} or {end}. Roll numbers must be 12 digits and start with '2456'.")

    if not roll_start_ranges or not roll_end_ranges or len(roll_start_ranges) != len(roll_end_ranges):
        errors.append("Invalid roll number ranges provided.")

    if errors:
        return render_template('e_admin.html', active_tab=active_tab, error_download_mid_marks=errors)

    if download_type == 'subject_wise':
        errors.append("Subject-wise view is not possible for mid marks.")

        return render_template('e_admin.html', active_tab=active_tab, error_download_mid_marks=errors)

    try:
        # Connect to the database
        conn = pymysql.connect(**db_config)
        cursor = conn.cursor()

        # Prepare query to fetch data
        roll_number_conditions = []
        for start, end in zip(roll_start_ranges, roll_end_ranges):
            roll_number_conditions.append(
                f"(roll_number BETWEEN {start} AND {end})")
        roll_number_filter = " OR ".join(roll_number_conditions)

        query = f"""
            SELECT roll_number, subject_name, cie1, cie2, assignment, avg, total, passed_out_year
            FROM internal_marks
            WHERE passed_out_year = %s AND ({roll_number_filter})
        """
        cursor.execute(query, (passed_out_year,))
        data = cursor.fetchall()

        if not data:
            errors.append("No records found for the given criteria.")
            return render_template('e_admin.html', active_tab=active_tab, error_download_mid_marks=errors)

        # Get student names from the profile table
        student_query = f"""
            SELECT roll_number, `STUDENT NAME`
            FROM profile
            WHERE roll_number IN ({','.join([str(roll) for roll in set(row['roll_number'] for row in data)])})
        """
        cursor.execute(student_query)
        student_names = {row['roll_number']: row['STUDENT NAME']
                         for row in cursor.fetchall()}

        # Prepare data to be displayed
        df = pd.DataFrame(data)

        columns = ['Roll Number', 'Name', 'Subject Name',
                   'CIE1', 'CIE2', 'Assignment', 'Average', 'Total']
        display_data = []
        for roll in df['roll_number'].unique():
            student_data = df[df['roll_number'] == roll]
            row = {'Roll Number': roll}

            if 'name' in selected_columns:
                row['Name'] = student_names.get(roll, 'N/A')

            for column in selected_columns:
                if column == 'subject_name':
                    # Grouping subject-wise data, ensuring subjects are correctly displayed
                    subjects = student_data['subject_name'].unique()
                    subject_marks = []
                    for subject in subjects:
                        subject_data = student_data[student_data['subject_name'] == subject]
                        subject_marks.append(
                            f"{subject}: CIE1-{subject_data['cie1'].iloc[0]}, CIE2-{subject_data['cie2'].iloc[0]}, Assignment-{subject_data['assignment'].iloc[0]}")

                    row['Subjects'] = "; ".join(subject_marks)
                elif column in student_data.columns:
                    row[column] = student_data[column].sum(
                    ) if column != 'subject_name' else student_data[column].tolist()

            display_data.append(row)

        # Ensure the columns are correctly passed to the template
        return render_template('view_mid_marks.html', data=display_data, columns=columns)

    except Exception as e:
        errors.append(f"An error occurred: {str(e)}")
        return render_template('e_admin.html', active_tab=active_tab, error_download_mid_marks=errors)


@app.route('/view_mid_marks_hod', methods=['GET', 'POST'])
def view_mid_marks_hod():
    if request.method == 'POST':
        roll_start_ranges = request.form.getlist('roll_start_mid[]')
        roll_end_ranges = request.form.getlist('roll_end_mid[]')
        passed_out_year = request.form['passed_out_year']

        # Validate input
        def is_valid_roll_number(roll_number):
            return len(str(roll_number)) == 12 and str(roll_number).startswith('2456')

        errors = []
        for start, end in zip(roll_start_ranges, roll_end_ranges):
            if not is_valid_roll_number(start) or not is_valid_roll_number(end):
                errors.append(
                    f"Invalid roll number format: {start} or {end}. Roll numbers must be 12 digits and start with '2456'."
                )

        if errors:
            return render_template('view_mid_marks_hod.html', errors=errors)

        try:
            conn = pymysql.connect(**db_config)
            cursor = conn.cursor()

            # Generate roll number filter
            roll_number_conditions = []
            for start, end in zip(roll_start_ranges, roll_end_ranges):
                roll_number_conditions.append(
                    f"(roll_number BETWEEN {start} AND {end})")
            roll_number_filter = " OR ".join(roll_number_conditions)

            # Query to fetch internal marks
            query = f"""
                SELECT roll_number, subject_name, cie1, cie2, assignment, avg, total, passed_out_year
                FROM internal_marks
                WHERE passed_out_year = %s AND ({roll_number_filter})
            """
            cursor.execute(query, (passed_out_year,))
            data = cursor.fetchall()

            if not data:
                errors.append("No records found for the given criteria.")
                return render_template('view_mid_marks_hod.html', errors=errors)

            # Get student names from the profile table
            roll_numbers = set(row['roll_number'] for row in data)
            student_query = f"""
                SELECT roll_number, STUDENT NAME AS name
                FROM profile
                WHERE roll_number IN ({','.join(map(str, roll_numbers))})
            """
            cursor.execute(student_query)
            student_names = {row['roll_number']: row['name']
                             for row in cursor.fetchall()}

            # Group subject data by roll number
            grouped_data = {}
            for row in data:
                roll_number = row['roll_number']
                subject_data = f"{row['subject_name']}: CIE1-{row['cie1']}, CIE2-{row['cie2']}, Assignment-{row['assignment']}"
                if roll_number not in grouped_data:
                    grouped_data[roll_number] = {
                        'name': student_names.get(roll_number, 'N/A'),
                        'subjects': []
                    }
                grouped_data[roll_number]['subjects'].append(subject_data)

            # Prepare final data for template
            final_data = []
            for roll_number, details in grouped_data.items():
                final_data.append({
                    'roll_number': roll_number,
                    'name': details['name'],
                    'subjects': "; ".join(details['subjects']),
                    'cie1': '',  # Optional, you can leave this empty or calculate based on CIE1 data
                    'cie2': '',
                    'avg': '',  # Optional
                    'assignment': '',  # Optional
                    'total': ''  # Optional
                })
            # Close database connection
            cursor.close()
            conn.close()

            # Pass data to the template
            columns = ['Roll Number', 'Name', 'Subjects',
                       'CIE1', 'CIE2', 'Average', 'Assignment', 'Total']
            print(data)
            print(student_names)

            return render_template('view_mid_marks_hod.html', data=final_data, columns=columns)

        except Exception as e:
            errors.append(f"An error occurred: {str(e)}")
            return render_template('view_mid_marks_hod.html', errors=errors)

    return render_template('view_mid_marks_hod.html')


@app.route('/get_students_results_hod_view', methods=['GET'])
def get_students_results_hod_view():
    roll_ranges = request.args.get('roll_ranges')
    passed_out_year = request.args.get('passed_out_year_1')
    print("Received roll_ranges:", roll_ranges)  # Debugging print
    print("Received passed_out_year:", passed_out_year)  # Debugging print

    if not roll_ranges or not passed_out_year:
        return render_template('view_mid_marks_hod.html', error_view_mid_marks_hod="Missing required fields")

    try:
        roll_ranges = json.loads(roll_ranges)

        valid_roll_ranges = []
        for range in roll_ranges:
            start, end = range.get('start'), range.get('end')
            if start and end and start != end:
                valid_roll_ranges.append(range)

        if not valid_roll_ranges:
            return render_template('view_mid_marks_hod.html',
                                   error_view_mid_marks_hod="Invalid or empty roll number ranges.")

        roll_number_conditions = [
            f"(roll_number BETWEEN {range['start']} AND {range['end']})" for range in valid_roll_ranges
        ]
        roll_number_filter = " OR ".join(roll_number_conditions)

        query = f"""
            SELECT roll_number, subject_name, 
                   COALESCE(cie1, 0) AS cie1, 
                   COALESCE(cie2, 0) AS cie2, 
                   COALESCE(assignment, 0) AS assignment, 
                   COALESCE(avg, 0) AS avg, 
                   COALESCE(total, 0) AS total, 
                   passed_out_year
            FROM internal_marks
            WHERE passed_out_year = %s AND ({roll_number_filter})
        """
        conn = pymysql.connect(**db_config)
        # Use DictCursor to get results as dictionaries
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute(query, (passed_out_year,))
        data = cursor.fetchall()

        print("Fetched Data:", data)  # Debugging print

        if not data:
            return render_template('view_mid_marks_hod.html', error_view_mid_marks_hod="No records found")

        roll_numbers = set(row['roll_number'] for row in data)
        student_query = f"""
            SELECT roll_number, `STUDENT NAME` AS name
            FROM profile
            WHERE roll_number IN ({','.join(map(str, roll_numbers))})
        """
        cursor.execute(student_query)
        student_names = {row['roll_number']: row['name']
                         for row in cursor.fetchall()}

        grouped_data = {}
        for row in data:
            roll_number = row['roll_number']
            subject_data = f"{row['subject_name']}: CIE1-{row['cie1']}, CIE2-{row['cie2']}, Assignment-{row['assignment']}"

            if roll_number not in grouped_data:
                grouped_data[roll_number] = {
                    'name': student_names.get(roll_number, 'N/A'),
                    'subjects': [],
                    'cie1': 0,
                    'cie2': 0,
                    'avg': 0,
                    'assignment': 0,
                    'total': 0
                }

            grouped_data[roll_number]['subjects'].append(subject_data)
            grouped_data[roll_number]['cie1'] += row['cie1']
            grouped_data[roll_number]['cie2'] += row['cie2']
            grouped_data[roll_number]['assignment'] += row['assignment']
            grouped_data[roll_number]['avg'] += row['avg']
            grouped_data[roll_number]['total'] += row['total']

        final_data = [
            {
                'roll_number': roll_number,
                'name': details['name'],
                'subjects': "; ".join(details['subjects']),
                'cie1': details['cie1'],
                'cie2': details['cie2'],
                'avg': details['avg'],
                'assignment': details['assignment'],
                'total': details['total']
            }
            for roll_number, details in grouped_data.items()
        ]

        print("Final Processed Data:", final_data)  # Debugging print

        cursor.close()
        conn.close()

        return render_template('view_mid_marks_hod.html', data=final_data,
                               columns=['Roll Number', 'Name', 'Subjects', 'CIE1', 'CIE2', 'Average', 'Assignment',
                                        'Total'])

    except Exception as e:
        print("Error:", str(e))  # Debugging print
        return render_template('view_mid_marks_hod.html', error_view_mid_marks_hod=f"An error occurred: {str(e)}")


@app.route('/get_students_results_branch_section', methods=['GET'])
def get_students_results_branch_section():
    branch = request.args.get('branch')
    section = request.args.get('section')
    passed_out_year = request.args.get('passed_out_year')

    if not branch or not section or not passed_out_year:
        return render_template('view_mid_marks_hod.html', error_view_mid_marks_hod="Missing required fields")

    try:
        conn = pymysql.connect(**db_config)
        # Use DictCursor to get results as dictionaries
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # Query to get roll numbers and names based on branch, section, and passed-out year
        query_roll_numbers = """
            SELECT roll_number, `Student Name`
            FROM profile
            WHERE Branch = %s AND Section = %s AND `Passed out year` = %s
        """
        cursor.execute(query_roll_numbers, (branch, section, passed_out_year))
        profiles = cursor.fetchall()

        if not profiles:
            return render_template('view_mid_marks_hod.html', error_view_mid_marks_hod="No students found for the specified criteria.")

        # Create a mapping of roll numbers to names
        roll_number_to_name = {
            profile['roll_number']: profile['Student Name'] for profile in profiles}
        roll_numbers = list(roll_number_to_name.keys())

        if not roll_numbers:
            return render_template('view_mid_marks_hod.html', error_view_mid_marks_hod="No records found.")

        # Query to fetch mid marks data for the roll numbers using parameterized query
        query_internal_marks = """
            SELECT roll_number, subject_name, 
                   COALESCE(cie1, 0) AS cie1, 
                   COALESCE(cie2, 0) AS cie2, 
                   COALESCE(assignment, 0) AS assignment, 
                   COALESCE(avg, 0) AS avg, 
                   COALESCE(total, 0) AS total, 
                   passed_out_year
            FROM internal_marks
            WHERE roll_number IN ({})
            AND passed_out_year = %s
        """.format(",".join(["%s"] * len(roll_numbers)))

        cursor.execute(query_internal_marks, (*roll_numbers, passed_out_year))
        data = cursor.fetchall()

        if not data:
            return render_template('view_mid_marks_hod.html', error_view_mid_marks_hod="No records found.")

        # Group subject data by roll number
        grouped_data = {}
        for row in data:
            roll_number = row['roll_number']
            subject_data = f"{row['subject_name']}: CIE1-{row['cie1']}, CIE2-{row['cie2']}, Assignment-{row['assignment']}"
            if roll_number not in grouped_data:
                grouped_data[roll_number] = {
                    'name': roll_number_to_name.get(roll_number, roll_number),
                    'subjects': [],
                    'cie1': 0,
                    'cie2': 0,
                    'assignment': 0,
                    'avg': 0,
                    'total': 0
                }

            grouped_data[roll_number]['subjects'].append(subject_data)
            grouped_data[roll_number]['cie1'] += row['cie1']
            grouped_data[roll_number]['cie2'] += row['cie2']
            grouped_data[roll_number]['assignment'] += row['assignment']
            grouped_data[roll_number]['avg'] += row['avg']
            grouped_data[roll_number]['total'] += row['total']

        # Prepare final data for template
        final_data = []
        for roll_number, details in grouped_data.items():
            final_data.append({
                'roll_number': roll_number,
                'name': details['name'],
                'subjects': "; ".join(details['subjects']),
                'cie1': details['cie1'],
                'cie2': details['cie2'],
                'avg': details['avg'],
                'assignment': details['assignment'],
                'total': details['total']
            })

        cursor.close()
        conn.close()

        # Pass data to the template for rendering
        columns = ['Roll Number', 'Name', 'Subjects',
                   'CIE1', 'CIE2', 'Average', 'Assignment', 'Total']
        return render_template('view_mid_marks_hod.html', data=final_data, columns=columns)

    except Exception as e:
        return render_template('view_mid_marks_hod.html', error_view_mid_marks_hod=f"An error occurred: {str(e)}")


@app.route('/view_mid_marks_eadmin', methods=['GET', 'POST'])
def view_mid_marks_eadmin():
    if request.method == 'POST':
        roll_start_ranges = request.form.getlist('roll_start_mid[]')
        roll_end_ranges = request.form.getlist('roll_end_mid[]')
        passed_out_year = request.form.get('passed_out_year')

        # Validate input
        def is_valid_roll_number(roll_number):
            return len(str(roll_number)) == 12 and str(roll_number).startswith('2456')

        errors = []
        for start, end in zip(roll_start_ranges, roll_end_ranges):
            if not is_valid_roll_number(start) or not is_valid_roll_number(end):
                errors.append(
                    f"Invalid roll number format: {start} or {end}. Roll numbers must be 12 digits and start with '2456'."
                )

        if errors:
            return render_template('view_mid_marks_eadmin.html', errors=errors)

        try:
            conn = pymysql.connect(**db_config)
            cursor = conn.cursor()

            # Generate roll number filter
            roll_number_conditions = []
            for start, end in zip(roll_start_ranges, roll_end_ranges):
                roll_number_conditions.append(
                    f"(roll_number BETWEEN {start} AND {end})")
            roll_number_filter = " OR ".join(roll_number_conditions)

            # Query to fetch internal marks
            query = f"""
                SELECT roll_number, subject_name, cie1, cie2, assignment, avg, total, passed_out_year
                FROM internal_marks
                WHERE passed_out_year = %s AND ({roll_number_filter})
            """
            cursor.execute(query, (passed_out_year,))
            data = cursor.fetchall()

            if not data:
                errors.append("No records found for the given criteria.")
                return render_template('view_mid_marks_eadmin.html', errors=errors)

            # Get student names from the profile table
            roll_numbers = set(row['roll_number'] for row in data)
            student_query = f"""
                SELECT roll_number, `STUDENT NAME` AS name
                FROM profile
                WHERE roll_number IN ({','.join(map(str, roll_numbers))})
            """
            cursor.execute(student_query)
            student_names = {row['roll_number']: row['name']
                             for row in cursor.fetchall()}

            # Group subject data by roll number
            grouped_data = {}
            for row in data:
                roll_number = row['roll_number']
                subject_data = f"{row['subject_name']}: CIE1-{row['cie1']}, CIE2-{row['cie2']}, Assignment-{row['assignment']}"
                if roll_number not in grouped_data:
                    grouped_data[roll_number] = {
                        'name': student_names.get(roll_number, 'N/A'),
                        'subjects': []
                    }
                grouped_data[roll_number]['subjects'].append(subject_data)

            # Prepare final data for template
            final_data = []
            for roll_number, details in grouped_data.items():
                final_data.append({
                    'roll_number': roll_number,
                    'name': details['name'],
                    'subjects': "; ".join(details['subjects']),
                    'cie1': '',  # Optional, you can leave this empty or calculate based on CIE1 data
                    'cie2': '',
                    'avg': '',  # Optional
                    'assignment': '',  # Optional
                    'total': ''  # Optional
                })
            # Close database connection
            cursor.close()
            conn.close()

            # Pass data to the template
            columns = ['Roll Number', 'Name', 'Subjects',
                       'CIE1', 'CIE2', 'Average', 'Assignment', 'Total']
            print(data)
            print(student_names)

            return render_template('view_mid_marks_eadmin.html', data=final_data, columns=columns)

        except Exception as e:
            errors.append(f"An error occurred: {str(e)}")
            return render_template('view_mid_marks_eadmin.html', errors=errors)

    return render_template('view_mid_marks_eadmin.html')


@app.route('/get_students_results_eadmin_view', methods=['GET'])
def get_students_results_eadmin_view():
    roll_ranges = request.args.get('roll_ranges')
    passed_out_year = request.args.get('passed_out_year')
    print(f"Received passed out year: {passed_out_year}")
    if not roll_ranges or not passed_out_year:
        return render_template('view_mid_marks_eadmin.html', error_view_mid_marks_eadmin="Missing required fields")

    try:
        # Convert string back to list of roll ranges
        roll_ranges = json.loads(roll_ranges)

        # Validate roll ranges to avoid empty ranges
        valid_roll_ranges = []
        for range in roll_ranges:
            start, end = range.get('start'), range.get('end')
            if start and end and start != end:  # Ensure both start and end are non-empty and not equal
                valid_roll_ranges.append(range)

        if not valid_roll_ranges:
            return render_template('view_mid_marks_eadmin.html', error_view_mid_marks_eadmin="Invalid or empty roll number ranges.")
        # Generate roll number filter from the valid roll ranges
        roll_number_conditions = []
        for range in valid_roll_ranges:
            roll_number_conditions.append(
                f"(roll_number BETWEEN {range['start']} AND {range['end']})")
        roll_number_filter = " OR ".join(roll_number_conditions)

        # Query to fetch mid marks data based on the roll number ranges and passed-out year
        query = f"""
            SELECT roll_number, subject_name, cie1, cie2, assignment, avg, total, passed_out_year
            FROM internal_marks
            WHERE passed_out_year = %s AND ({roll_number_filter})
        """
        conn = pymysql.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute(query, (passed_out_year,))
        data = cursor.fetchall()

        if not data:
            return render_template('view_mid_marks_eadmin.html', error_view_mid_marks_eadmin="No records found")

        # Get student names from the profile table
        roll_numbers = set(row['roll_number'] for row in data)
        student_query = f"""
            SELECT roll_number, `STUDENT NAME` AS name
            FROM profile
            WHERE roll_number IN ({','.join(map(str, roll_numbers))})
        """
        cursor.execute(student_query)
        student_names = {row['roll_number']: row['name']
                         for row in cursor.fetchall()}

        # Group subject data by roll number and associate student names
        grouped_data = {}
        for row in data:
            roll_number = row['roll_number']
            subject_data = f"{row['subject_name']}: CIE1-{row['cie1']}, CIE2-{row['cie2']}, Assignment-{row['assignment']}"
            if roll_number not in grouped_data:
                grouped_data[roll_number] = {
                    'name': student_names.get(roll_number, 'N/A'),
                    'subjects': [],
                    'cie1': 0,
                    'cie2': 0,
                    'avg': 0,
                    'assignment': 0,
                    'total': 0
                }

            # Add subject data and individual marks to the grouped data
            grouped_data[roll_number]['subjects'].append(subject_data)
            grouped_data[roll_number]['cie1'] += row['cie1']
            grouped_data[roll_number]['cie2'] += row['cie2']
            grouped_data[roll_number]['assignment'] += row['assignment']
            grouped_data[roll_number]['avg'] += row['avg']
            grouped_data[roll_number]['total'] += row['total']

        # Prepare final data for template
        final_data = []
        for roll_number, details in grouped_data.items():
            final_data.append({
                'roll_number': roll_number,
                'name': details['name'],
                'subjects': "; ".join(details['subjects']),
                'cie1': details['cie1'],  # Total CIE1 marks
                'cie2': details['cie2'],  # Total CIE2 marks
                'avg': details['avg'],  # Total Average
                'assignment': details['assignment'],  # Total Assignment marks
                'total': details['total']  # Total marks
            })

        cursor.close()
        conn.close()

        # Pass data to the template for rendering
        columns = ['Roll Number', 'Name', 'Subjects',
                   'CIE1', 'CIE2', 'Average', 'Assignment', 'Total']
        return render_template('view_mid_marks_eadmin.html', data=final_data, columns=columns)

    except Exception as e:
        return render_template('view_mid_marks_eadmin.html', error_view_mid_marks_eadmin=f"An error occurred: {str(e)}")


@app.route('/get_students_results_hod', methods=['POST'])
def get_students_results_hod():
    try:
        # Determine result type
        result_type = request.form['result_type']

        # Common database connection
        connection = pymysql.connect(**db_config)
        cursor = connection.cursor()

        if result_type == 'subject-wise':
            # Handle Subject-wise results
            subject_code = request.form['subject']
            year_branch = request.form['year_branch']
            passed_out_year, branch_section = year_branch.split('-')
            branch, section = branch_section.split()

            # Fetch semester based on subject
            semester_query = "SELECT semester FROM subject WHERE subject_code = %s"
            cursor.execute(semester_query, (subject_code,))
            semester_result = cursor.fetchone()

            if not semester_result or not semester_result.get('semester'):
                return jsonify({'error': f"Semester not found for subject code: {subject_code}"}), 400

            semester = semester_result['semester']

            # Fetch student details
            student_query = """
                SELECT `STUDENT NAME` AS name, roll_number 
                FROM profile 
                WHERE Branch = %s AND Section = %s AND `Passed out year` = %s
            """
            cursor.execute(student_query, (branch, section, passed_out_year))
            students = cursor.fetchall()

            if not students:
                return render_template('no_students.html')

            # Fetch marks for the selected subject
            marks_query = """
                SELECT roll_number, cie1, cie2, assignment, avg, total 
                FROM internal_marks 
                WHERE subject_code = %s AND semester = %s AND passed_out_year = %s
            """
            cursor.execute(marks_query, (subject_code,
                           semester, passed_out_year))
            marks_data = cursor.fetchall()

            marks_dict = {row['roll_number']: row for row in marks_data}

            for student in students:
                roll_number = student['roll_number']
                student['marks'] = marks_dict.get(roll_number, {
                    'cie1': None, 'cie2': None, 'assignment': None, 'avg': None, 'total': None
                })

            subject_query = "SELECT subject_name FROM subject WHERE subject_code = %s"
            cursor.execute(subject_query, (subject_code,))
            subject_name = cursor.fetchone().get('subject_name', None)

            return render_template(
                'midmarks_view_hod.html',
                students=students,
                subject_name=subject_name,
                subject_code=subject_code,
                semester=semester,
                passed_out_year=passed_out_year,
                branch=branch,
                section=section
            )

        elif result_type == 'all-subjects':

            year = request.form['year']
            semester = request.form['semester']

            # Establish database connection
            connection = pymysql.connect(**db_config)
            cursor = connection.cursor()

            # Fetch the total marks for each subject
            marks_query = """
                        SELECT roll_number, subject_name, total 
                        FROM internal_marks 
                        WHERE passed_out_year = %s AND semester = %s
                    """
            cursor.execute(marks_query, (year, semester))
            marks_data = cursor.fetchall()

            if not marks_data:
                return render_template('no_results.html')

            # Organize data by roll number and subject, and sum the totals for each subject
            student_data = {}
            subject_list = set()

            for row in marks_data:
                roll_number = row['roll_number']
                subject_name = row['subject_name']
                total = row['total']

                if roll_number not in student_data:
                    student_data[roll_number] = {
                        'roll_number': roll_number, 'subjects': {}}

                if subject_name not in student_data[roll_number]['subjects']:
                    student_data[roll_number]['subjects'][subject_name] = 0

                # Add the total for this subject to the roll number's existing total
                student_data[roll_number]['subjects'][subject_name] += total

                subject_list.add(subject_name)

            # Convert subject_list to a sorted list for consistent column ordering
            subject_list = sorted(subject_list)

            return render_template('hod.html', student_data=student_data, subject_list=subject_list,
                                   year=year, semester=semester)

    except Exception as e:
        return jsonify({'error': f"An error occurred: {e}"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route('/view_faculty', methods=['GET', 'POST'])
def view_faculty():
    active_tab = 'view_faculty'
    # Get the search query from the form
    search_query = request.form.get('search', '')
    download = request.args.get('download', False)
    results = []
    try:
        connection = pymysql.connect(**db_config)
        cursor = connection.cursor()

        query = """
        SELECT 
            f.faculty_id,
            f.first_name,
            f.last_name,
            f.email,
            f.phone_number,
            f.department_id,
            f.designation,
            f.joining_date,
            f.salary,
            f.roles,
            f.status,
            fa.assessment_data,
            GROUP_CONCAT(DISTINCT s.subject_name SEPARATOR ', ') AS subjects
        FROM 
            faculty_user f
        LEFT JOIN 
            faculty_assessment fa 
        ON 
            f.faculty_id = fa.faculty_id
        LEFT JOIN 
            subject s 
        ON 
            f.department_id = s.department_id
        """

        if search_query:
            query += """
            WHERE 
                f.faculty_id LIKE %s
                OR f.first_name LIKE %s 
                OR f.last_name LIKE %s 
            """

        query += " GROUP BY f.faculty_id"

        if search_query:
            cursor.execute(
                query, (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))
        else:
            cursor.execute(query)

        results = cursor.fetchall()

        # Convert results to a dictionary
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in results]

        print(results)  # Debugging output

    except pymysql.MySQLError as err:
        print(f"Error: {err}")
        results = []
    finally:
        cursor.close()
        connection.close()

    # Handle download request
    if download:
        # Convert results to a DataFrame
        df = pd.DataFrame(results)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='FacultyDetails')

        output.seek(0)
        return send_file(
            output,
            as_attachment=True,
            download_name='faculty_details.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    return render_template('hod.html', data=results, search_query=search_query, active_tab=active_tab)


@app.route('/delete_mid_marks', methods=['GET', 'POST'])
def delete_mid_marks():
    error_delete_mid_marks = None
    success_delete_mid_marks = None
    active_years = []
    roll_numbers_to_display = []

    try:
        # Fetch distinct years from the database
        conn = pymysql.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT passed_out_year FROM internal_marks ORDER BY passed_out_year DESC")
        active_years = [row[0] for row in cursor.fetchall()]
    except pymysql.MySQLError as e:
        error_delete_mid_marks = f"Database error while fetching years: {str(e)}"
    except Exception as e:
        error_delete_mid_marks = f"Unexpected error while fetching years: {str(e)}"
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    if request.method == 'POST':
        # Get the semester and passed-out year from the form
        semester = request.form.get('semester')
        passed_out_year = request.form.get('passed_out_year')

        # Validate inputs
        if not semester or not passed_out_year:
            error_delete_mid_marks = "Please fill out all fields."
            return render_template(
                'e_admin.html',
                active_years=active_years,
                error_delete_mid_marks=error_delete_mid_marks,
                active_tab='delete_mid_marks',
            )

        try:
            # Connect to the database
            conn = pymysql.connect(**db_config)
            cursor = conn.cursor()

            # Check if data exists for the given semester and year
            check_query = """
                SELECT COUNT(*) FROM internal_marks
                WHERE semester = %s AND passed_out_year = %s
            """
            cursor.execute(check_query, (semester, passed_out_year))
            count = cursor.fetchone()[0]

            if count == 0:
                error_delete_mid_marks = "No records found for the given Semester and Passed Out Year."
            else:
                # Get all roll numbers for the given semester and passed-out year
                get_roll_numbers_query = """
                    SELECT DISTINCT roll_number FROM internal_marks
                    WHERE semester = %s AND passed_out_year = %s
                """
                cursor.execute(get_roll_numbers_query,
                               (semester, passed_out_year))
                roll_numbers = [row[0] for row in cursor.fetchall()]

                # Check for supply status for each roll number in the specified semester
                supply_roll_numbers = []
                for roll_number in roll_numbers:
                    supply_check_query = f"""
                        SELECT COUNT(*) FROM sem{semester}
                        WHERE roll_number = %s AND exam_series = 'supply'
                    """
                    cursor.execute(supply_check_query, (roll_number,))
                    supply_count = cursor.fetchone()[0]

                    # If at least one record has 'supply', add roll_number to the supply list
                    if supply_count > 0:
                        supply_roll_numbers.append(roll_number)

                # Delete records excluding those with "supply"
                if supply_roll_numbers:
                    delete_query = f"""
                        DELETE FROM internal_marks
                        WHERE semester = %s AND passed_out_year = %s
                        AND roll_number NOT IN ({','.join(['%s'] * len(supply_roll_numbers))})
                    """
                    cursor.execute(
                        delete_query, (semester, passed_out_year, *supply_roll_numbers))
                else:
                    delete_query = """
                        DELETE FROM internal_marks
                        WHERE semester = %s AND passed_out_year = %s
                    """
                    cursor.execute(delete_query, (semester, passed_out_year))

                conn.commit()
                success_delete_mid_marks = (
                    f"Successfully deleted {cursor.rowcount} record(s) for Semester {semester}, Passed Out Year {passed_out_year}."
                )

                # Fetch roll numbers that are still present after deletion
                cursor.execute(get_roll_numbers_query,
                               (semester, passed_out_year))
                roll_numbers_to_display = [row[0]
                                           for row in cursor.fetchall()]

        except pymysql.MySQLError as e:
            error_delete_mid_marks = f"Database error: {str(e)}"
        except Exception as e:
            error_delete_mid_marks = f"An unexpected error occurred: {str(e)}"
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

        return render_template(
            'e_admin.html',
            active_years=active_years,
            error_delete_mid_marks=error_delete_mid_marks,
            success_delete_mid_marks=success_delete_mid_marks,
            active_tab='delete_mid_marks',
            # Pass the updated roll numbers to display
            roll_numbers_to_display=roll_numbers_to_display
        )

    # Render the page initially
    return render_template(
        'e_admin.html',
        active_years=active_years,
        error_delete_mid_marks=error_delete_mid_marks,
        active_tab='delete_mid_marks',
    )


@app.route('/get_years_fa', methods=['GET'])
def get_years_fa():
    try:
        app.logger.info("get_years_fa endpoint called")
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Get unique years from profile table
        cursor.execute("SELECT DISTINCT `Passed out year` FROM profile ORDER BY `Passed out year` DESC")
        years = [row['Passed out year'] for row in cursor.fetchall()]
        
        app.logger.info(f"Found years: {years}")
        return jsonify(years)
        
    except Exception as e:
        app.logger.error(f"Error in get_years_fa: {str(e)}")
        return jsonify({'error': str(e)}), 500
        
    finally:
        if 'connection' in locals() and connection:
            cursor.close()
            connection.close()

@app.route('/get_branches_fa', methods=['POST'])
def get_branches_fa():
    data = request.json
    year = data.get('year')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch branches for the selected year
    cursor.execute(
        "SELECT branch_section FROM year_branch_section WHERE active_year = %s", (year,))
    result = cursor.fetchone()
    branches = list(json.loads(
        result['branch_section']).keys()) if result else []

    conn.close()
    return jsonify(branches)


@app.route('/get_sections_fa', methods=['POST'])
def get_sections_fa():
    data = request.json
    year = data.get('year')
    branch = data.get('branch')

    if not year or not branch:
        return jsonify({'error': 'Year and branch are required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch sections for the selected year and branch
    cursor.execute(
        "SELECT branch_section FROM year_branch_section WHERE active_year = %s", (year,))
    result = cursor.fetchone()
    print(f"Query Result for year={year}: {result}")  # Debugging

    sections = []
    if result:
        branch_section_data = json.loads(result['branch_section'])
        print(f"Branch Section Data: {branch_section_data}")  # Debugging
        sections = branch_section_data.get(branch, [])
        print(f"Sections for branch={branch}: {sections}")  # Debugging

    conn.close()
    return jsonify(sections)


@app.route('/get_subjects_by_branch_and_semester_fa', methods=['POST'])
def get_subjects_by_branch_and_semester_fa():
    data = request.json
    branch = data.get('branch')
    semester = data.get('semester')

    if not branch or not semester:
        return jsonify({'error': 'Branch and semester are required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch department_id based on the branch
    cursor.execute(
        "SELECT department_id FROM department WHERE department_name = %s", (branch,))
    department = cursor.fetchone()

    if not department:
        conn.close()
        return jsonify({'error': 'No department found for the selected branch'}), 400

    department_id = department['department_id']

    # Fetch subjects for the department and semester
    cursor.execute(
        "SELECT subject_id, subject_name FROM subject WHERE department_id = %s AND semester = %s",
        (department_id, semester)
    )
    subjects = cursor.fetchall()

    conn.close()
    return jsonify(subjects)


@app.route('/assign_faculty_fa', methods=['POST'])
def assign_faculty_fa():
    try:
        data = request.get_json()
        if not data or 'faculty_id' not in data or 'assignments' not in data:
            return jsonify({"message": "Invalid request data"}), 400
        print("Received data:", data)  # Debugging line

        faculty_id = data.get('faculty_id')
        assignments = data.get('assignments')

        # Validate faculty_id and assignments
        if not faculty_id:
            return jsonify({'error': 'Faculty ID is required.'}), 400
        if not assignments or not isinstance(assignments, list):
            return jsonify({'error': 'Assignments must be a non-empty list.'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        assessment_data = {}  # Reset assessment data for faculty

        for assignment in assignments:
            year_branch_section = assignment.get('year_branch_section')
            subject_id = assignment.get('subject_id')

            # Validate year_branch_section and subject_id
            if not year_branch_section or not subject_id:
                conn.close()
                return jsonify({'error': 'Each assignment must include year_branch_section and subject_id.'}), 400
            if '-' not in year_branch_section:
                conn.close()
                return jsonify({
                    'error': f'Invalid year_branch_section format: {year_branch_section}. Expected format: year-branch-section.'}), 400

            try:
                year, branch, section = year_branch_section.split('-')
                # Debugging line
                print(
                    f"Split into year: {year}, branch: {branch}, section: {section}")
            except ValueError:
                conn.close()
                return jsonify({
                    'error': f'Invalid year_branch_section format: {year_branch_section}. Expected format: year-branch-section.'
                }), 400

            # Fetch the subject code from the subject table
            cursor.execute(
                "SELECT subject_code FROM subject WHERE subject_id = %s", (subject_id,))
            subject = cursor.fetchone()

            if not subject:
                conn.close()
                return jsonify({'error': f'Subject not found for subject_id: {subject_id}.'}), 400

            subject_code = subject['subject_code']
            print(f"Found subject_code: {subject_code}")  # Debugging line

            # Build the new assessment_data
            if subject_code not in assessment_data:
                assessment_data[subject_code] = {}

            if year not in assessment_data[subject_code]:
                assessment_data[subject_code][year] = []

            assessment_data[subject_code][year].append(f"{branch} {section}")

        # Check if faculty_id already exists in faculty_assessment
        cursor.execute(
            "SELECT faculty_id FROM faculty_assessment WHERE faculty_id = %s", (faculty_id,))
        faculty_exists = cursor.fetchone()

        if faculty_exists:
            # Replace existing assessment_data
            cursor.execute(
                "UPDATE faculty_assessment SET assessment_data = %s, updated_at = NOW() WHERE faculty_id = %s",
                (json.dumps(assessment_data), faculty_id)
            )
            print("Replaced assessment_data for faculty.")  # Debugging line
        else:
            # Insert new entry if faculty does not exist
            cursor.execute(
                "INSERT INTO faculty_assessment (faculty_id, assessment_data, created_at, updated_at) VALUES (%s, %s, NOW(), NOW())",
                (faculty_id, json.dumps(assessment_data))
            )
            print("Created new assessment_data for faculty.")  # Debugging line

        conn.commit()
        conn.close()

        return jsonify({"message": "Faculty assigned successfully!"})
    except Exception as e:
        print("Error:", str(e))  # Log the error
        return jsonify({"message": "An error occurred while processing the request"}), 500

@app.route('/get_faculty_assignments', methods=['POST'])
def get_faculty_assignments():
    data = request.json
    faculty_id = data.get('faculty_id')

    if not faculty_id:
        return jsonify({'error': 'Faculty ID is required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)


    # Debugging: Print faculty_id
    print(f"Faculty ID received: {faculty_id}")

    cursor.execute(
        "SELECT assessment_data FROM faculty_assessment WHERE faculty_id = %s", (faculty_id,)
    )
    result = cursor.fetchone()

    # Debugging: Print result from SQL
    print(f"SQL Query Result: {result}")

    if not result or not result['assessment_data']:
        conn.close()
        print("No data found for faculty_id:", faculty_id)  # Debugging log
        return jsonify([])  # Return an empty array

    try:
        assessment_data = json.loads(result['assessment_data'])  # Parse JSON
    except json.JSONDecodeError as e:
        conn.close()
        print(f"JSON Decode Error: {e}")  # Debugging log
        return jsonify({'error': 'Invalid JSON data'}), 500

    assignments = []

    for subject_code, years in assessment_data.items():
        cursor.execute("SELECT subject_name FROM subject WHERE subject_code = %s", (subject_code,))
        subject_result = cursor.fetchone()

        subject_name = subject_result['subject_name'] if subject_result else "Unknown"

        for year, branches in years.items():
            for branch in branches:
                assignments.append({
                    "subject": f"{subject_code} ({subject_name})",
                    "year": year,
                    "branch_section": branch
                })

    conn.close()
    print(f"Final Assignments Data: {assignments}")  # Debugging log
    return jsonify(assignments)


@app.route("/assign_elective_subjects", methods=["POST"])
def assign_elective_subjects():
    try:
        data = request.get_json()
        print("Received Data:", data)

        if not data:
            return jsonify({"error": "Invalid JSON or missing request body"}), 400

        year = data.get("year")
        branch = data.get("branch")
        semester = data.get("semester")
        subject_names = data.get("subjects", [])  # List of subject names

        print(f"Year: {year}, Branch: {branch}, Semester: {semester}, Subjects: {subject_names}")

        if not year or not branch or not semester or not subject_names:
            return jsonify({"error": "Year, branch, semester, and subjects are required"}), 400

        connection = pymysql.connect(**db_config)
        cursor = connection.cursor()

        # Check if electives are already assigned for this year and branch
        cursor.execute(
            "SELECT 1 FROM assigned_elective_access WHERE year = %s AND branch = %s",
            (year, branch),
        )
        existing_entry = cursor.fetchone()

        if existing_entry:
            return jsonify({"error": "Elective subjects already assigned for this year and branch"}), 400

        # Fetch subject codes from the database
        subjects = []
        for subject_name in subject_names:
            cursor.execute(
                "SELECT subject_code FROM subject WHERE subject_name = %s AND department_id = %s AND semester = %s AND elective = %s",
                (subject_name, branch, semester, "open elective"),
            )

            subject_data = cursor.fetchone()
            if subject_data:
                subjects.append({"subject_code": subject_data[0], "subject_name": subject_name})
            else:
                return jsonify({"error": f"Subject '{subject_name}' not found for this department and semester"}), 404

        # Store the subjects in JSON format
        subjects_json = json.dumps(subjects)
        cursor.execute(
            "INSERT INTO assigned_elective_access (year, branch, semester, subjects) VALUES (%s, %s, %s, %s)",
            (year, branch, semester, subjects_json),
        )
        connection.commit()

        response = {"success": "Elective subjects assigned successfully!"}
    except pymysql.MySQLError as e:
        print("Database Error:", str(e))
        connection.rollback()
        response = {"error": "Database error: " + str(e)}
    except Exception as e:
        print("Unexpected Error:", str(e))
        response = {"error": "Unexpected error: " + str(e)}
    finally:
        cursor.close()
        connection.close()

    return jsonify(response)


@app.route('/get_electives')
def get_electives():
    roll_number = session.get('username')

    if not roll_number:
        return jsonify({"error": "Please log in first."}), 403

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT `Passed out year` AS passed_out_year FROM profile WHERE roll_number = %s", (roll_number,))
            user_data = cursor.fetchone()

            if not user_data:
                return jsonify({"error": "User not found in profile table."}), 404

            passed_out_year = user_data['passed_out_year']

            # Fetch active years
            cursor.execute("SELECT year FROM active_years ORDER BY year DESC")
            active_years = [row['year'] for row in cursor.fetchall()]

            if passed_out_year not in active_years:
                return jsonify({"subjects": []})

            # Get year rank
            year_rank = active_years.index(passed_out_year) + 1



            # Fetch elective subjects
            cursor.execute(
                "SELECT subjects FROM assigned_elective_access WHERE year = %s",
                (passed_out_year)
            )
            subjects_data = cursor.fetchone()

            subjects = json.loads(subjects_data['subjects']) if subjects_data and subjects_data['subjects'] else []

            return jsonify({"subjects": subjects})

    finally:
        connection.close()


# Fetch Assigned Elective Subjects
@app.route('/get_assigned_elective_subjects', methods=['GET'])
def get_assigned_elective_subjects():
    connection = pymysql.connect(**db_config)
    cursor = connection.cursor()

    cursor.execute("SELECT id, year, branch, semester, subjects FROM assigned_elective_access")
    electives = cursor.fetchall()

    cursor.close()
    connection.close()

    # Convert tuples to a list of dictionaries, extracting only subject names
    elective_list = [
        {
            "id": row[0],
            "year": row[1],
            "branch": row[2],
            "semester": row[3],
            "subjects": [subject["subject_name"] for subject in json.loads(row[4])]
        }
        for row in electives
    ]

    return jsonify(elective_list)


# Delete an Assigned Elective based on year, branch, semester
@app.route('/delete_elective_subject', methods=['POST'])
def delete_elective_subject():
    data = request.get_json()
    year = data.get('year')
    branch = data.get('branch')
    semester = data.get('semester')

    if not (year and branch and semester):
        return jsonify({"error": "Year, branch, and semester are required"}), 400

    connection = pymysql.connect(**db_config)
    cursor = connection.cursor()

    try:
        cursor.execute("DELETE FROM assigned_elective_access WHERE year = %s AND branch = %s AND semester = %s",
                       (year, branch, semester))
        connection.commit()

        if cursor.rowcount > 0:
            response = {"success": "Elective deleted successfully"}
        else:
            response = {"error": "No matching elective found"}

    except pymysql.Error as e:
        connection.rollback()
        response = {"error": str(e)}

    cursor.close()
    connection.close()

    return jsonify(response)

# Fetch Branches
@app.route('/get_branches', methods=['GET'])
def get_branches():
    connection = pymysql.connect(**db_config)
    cursor = connection.cursor()
    cursor.execute("SELECT DISTINCT department_id FROM subject")
    branches = [{"branch": row[0]} for row in cursor.fetchall()]
    cursor.close()
    connection.close()
    return jsonify(branches)


@app.route('/get_semesters_with_electives', methods=['GET'])
def get_semesters_with_electives():
    branch = request.args.get('branch')

    if not branch:
        return jsonify({"error": "Branch is required"}), 400

    connection = pymysql.connect(**db_config)
    cursor = connection.cursor()

    # Corrected SQL query
    cursor.execute(
        "SELECT DISTINCT semester FROM subject WHERE department_id = %s AND elective = 'Open Elective'", (branch,))

    semesters = [{"semester": row[0]} for row in cursor.fetchall()]

    cursor.close()
    connection.close()

    return jsonify(semesters)


# Fetch Elective Subjects based on Branch and Semester
@app.route('/get_elective_subjects', methods=['GET'])
def get_elective_subjects():
    branch = request.args.get('branch')
    semester = request.args.get('semester')

    if not branch or not semester:
        return jsonify({"error": "Branch and semester are required"}), 400

    connection = pymysql.connect(**db_config)
    cursor = connection.cursor()
    cursor.execute(
        "SELECT subject_name FROM subject WHERE department_id = %s AND semester = %s AND elective = 'Open Elective'",
        (branch, semester),
    )
    subjects = [{"subject": row[0]} for row in cursor.fetchall()]
    cursor.close()
    connection.close()
    return jsonify(subjects)


@app.route('/get_active_years_hod', methods=['GET'])
def get_active_years():
    connection = pymysql.connect(**db_config)
    cursor = connection.cursor()
    cursor.execute("SELECT year FROM active_years")
    active_years = [{"year": row[0]}
                    for row in cursor.fetchall()]  # Convert to dictionary list
    cursor.close()
    connection.close()
    return jsonify(active_years)




@app.route('/show_electives')
def show_electives():
    roll_number = session.get('username')

    if not roll_number:
        return "Please log in first.", 403

    error_scrape = request.args.get('error_scrape')
    success_scrape = request.args.get('success_scrape')

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Fetch student's passed out year
            cursor.execute(
                "SELECT `Passed out year` AS passed_out_year FROM profile WHERE roll_number = %s", (roll_number,))
            user_data = cursor.fetchone()

            if not user_data:
                return "User not found in profile table.", 404

            passed_out_year = user_data['passed_out_year']

            # Fetch active years sorted in descending order
            cursor.execute("SELECT year FROM active_years ORDER BY year DESC")
            active_years = [row['year'] for row in cursor.fetchall()]

            if passed_out_year not in active_years:
                return render_template("electives.html", can_edit=False, subjects=[],
                                       error_scrape=error_scrape, success_scrape=success_scrape)

            # Fetch elective subjects (includes subject_code)
            cursor.execute(
                "SELECT subjects FROM assigned_elective_access WHERE year = %s",
                (passed_out_year,)
            )
            subjects_data = cursor.fetchone()

            # Parse subjects from JSON
            subjects = json.loads(subjects_data['subjects']) if subjects_data and subjects_data['subjects'] else []

            # Fetch the already selected subject for the student
            cursor.execute(
                "SELECT subject_code FROM student_electives WHERE roll_number = %s",
                (roll_number,)
            )
            selected_subject_data = cursor.fetchone()
            selected_subject_code = selected_subject_data['subject_code'] if selected_subject_data else None

            return render_template("electives.html", subjects=subjects, can_edit=bool(subjects),
                                   selected_subject_code=selected_subject_code,
                                   error_scrape=error_scrape, success_scrape=success_scrape)

    finally:
        connection.close()


@app.route('/update_elective', methods=['POST'])
def update_elective():
    roll_number = session.get('username')
    subject_name = request.form.get('subject')

    error_scrape = request.args.get('error_scrape')
    success_scrape = request.args.get('success_scrape')

    if not roll_number:
        error_scrape = "Please log in first."
        return redirect(url_for('show_electives', error_scrape=error_scrape, success_scrape=success_scrape))

    if not subject_name:
        error_scrape = "Please select a subject."
        return redirect(url_for('show_electives', error_scrape=error_scrape, success_scrape=success_scrape))

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Get the passed out year of the student
            cursor.execute("SELECT `Passed out year` AS passed_out_year FROM profile WHERE roll_number = %s", (roll_number,))
            user_data = cursor.fetchone()

            if not user_data:
                error_scrape = "User not found in profile table."
                return redirect(url_for('show_electives', error_scrape=error_scrape, success_scrape=success_scrape))

            passed_out_year = user_data['passed_out_year']

            # Fetch subjects from assigned_elective_access for the user's passed out year
            cursor.execute("SELECT subjects FROM assigned_elective_access WHERE year = %s", (passed_out_year,))
            subjects_data = cursor.fetchone()

            if not subjects_data or not subjects_data['subjects']:
                error_scrape = "Elective subjects not found."
                return redirect(url_for('show_electives', error_scrape=error_scrape, success_scrape=success_scrape))

            subjects = json.loads(subjects_data['subjects'])

            # Find the subject code based on the selected subject name
            subject_code = next((sub['subject_code'] for sub in subjects if sub['subject_name'] == subject_name), None)

            if not subject_code:
                error_scrape = "Invalid subject selection."
                return redirect(url_for('show_electives', error_scrape=error_scrape, success_scrape=success_scrape))

            # Check if roll number already exists in student_electives
            cursor.execute("SELECT COUNT(*) as count FROM student_electives WHERE roll_number = %s", (roll_number,))
            exists = cursor.fetchone()["count"] > 0  # True if roll number exists

            if exists:
                # Update the subject_code if the roll number already exists
                cursor.execute("UPDATE student_electives SET subject_code = %s WHERE roll_number = %s",
                               (subject_code, roll_number))
            else:
                # Insert a new record if roll number does not exist
                cursor.execute("INSERT INTO student_electives (roll_number, subject_code) VALUES (%s, %s)",
                               (roll_number, subject_code))

            connection.commit()
            success_scrape = "Elective subject updated successfully."

    except Exception as e:
        connection.rollback()
        error_scrape = f"Error updating elective: {str(e)}"
    finally:
        connection.close()

    return redirect(url_for('show_electives', error_scrape=error_scrape, success_scrape=success_scrape))


@app.route('/check_electives')
def check_electives():
    roll_number = session.get('username')

    if not roll_number:
        return jsonify({"can_edit": False})  # No user logged in

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Get the user's passed-out year
            cursor.execute(
                "SELECT `Passed out year` FROM profile WHERE roll_number = %s", (roll_number,))
            user_data = cursor.fetchone()

            if not user_data:
                return jsonify({"can_edit": False})  # User not found

            passed_out_year = int(user_data['Passed out year'])

            # Fetch all active years and determine the student's rank
            cursor.execute("SELECT year FROM active_years ORDER BY year DESC")
            active_years = [int(row['year']) for row in cursor.fetchall()]

            if passed_out_year not in active_years:
                return jsonify({"can_edit": False})

            # Check if electives exist for this year
            cursor.execute(
                "SELECT 1 FROM assigned_elective_access WHERE year = %s",
                (passed_out_year,)
            )
            elective_data = cursor.fetchone()

            return jsonify({"can_edit": bool(elective_data)})
    finally:
        connection.close()

@app.route('/student_subjects')
def student_subjects():
    roll_number = session.get('username')
    if not roll_number:
        return "User not logged in.", 403

    db = get_db_connection()
    cursor = db.cursor()

    try:
        # Fetch student details
        cursor.execute("""
            SELECT `Passed out year` AS passed_out_year, Branch, Section 
            FROM profile 
            WHERE roll_number = %s
        """, (roll_number,))
        user_data = cursor.fetchone()

        if not user_data:
            return "User not found in profile table.", 404

        passed_out_year = str(user_data['passed_out_year']).strip()
        student_section = f"{user_data['Branch'].strip()} {user_data['Section'].strip()}"

        app.logger.info(f"User Data: {user_data}")

        # Fetch faculty assessment data
        cursor.execute("SELECT faculty_id, assessment_data FROM faculty_assessment")
        faculty_data = cursor.fetchall()

        faculty_subjects, subject_codes, faculty_ids = [], set(), set()
        open_elective_codes = set()

        # Identify Open Elective Subjects
        cursor.execute("""
            SELECT subject_code 
            FROM subject 
            WHERE elective = 'Open Elective'
        """)
        open_elective_results = cursor.fetchall()
        open_elective_codes = {str(row['subject_code']).strip() for row in open_elective_results}

        for row in faculty_data:
            try:
                assessment_json = json.loads(row['assessment_data'])
                for subject_code, year_data in assessment_json.items():
                    subject_code_str = str(subject_code).strip()
                    if passed_out_year in year_data and student_section in year_data[passed_out_year]:
                        faculty_subjects.append({"faculty_id": row['faculty_id'], "subject_code": subject_code_str})
                        subject_codes.add(subject_code_str)
                        faculty_ids.add(row['faculty_id'])
            except json.JSONDecodeError:
                continue  # Skip faulty JSON

        # Check student's elective choice
        cursor.execute("""
            SELECT subject_code 
            FROM student_electives 
            WHERE roll_number = %s
        """, (roll_number,))
        student_electives = {str(row['subject_code']).strip() for row in cursor.fetchall()}

        # Filtering Open Elective Subjects
        chosen_elective = next((code for code in student_electives if code in open_elective_codes), None)
        if chosen_elective:
            faculty_subjects = [entry for entry in faculty_subjects if entry["subject_code"] == chosen_elective or entry["subject_code"] not in open_elective_codes]
        else:
            faculty_subjects = [entry for entry in faculty_subjects if entry["subject_code"] not in open_elective_codes]

        if not faculty_subjects:
            return "No subjects found for student.", 404

        # Fetch faculty names in bulk
        faculty_map = {}
        if faculty_ids:
            format_strings = ', '.join(['%s'] * len(faculty_ids))
            faculty_query = f"""
                SELECT faculty_id, CONCAT(first_name, ' ', last_name) AS faculty_name
                FROM faculty_user 
                WHERE faculty_id IN ({format_strings})
            """
            cursor.execute(faculty_query, tuple(faculty_ids))
            faculty_map = {row['faculty_id']: row['faculty_name'] for row in cursor.fetchall()}

        # Fetch subject details in bulk
        subject_map = {}
        if subject_codes:
            subject_query = f"""
                SELECT subject_code, subject_name, credits, elective
                FROM subject
                WHERE subject_code IN ({', '.join(['%s'] * len(subject_codes))})
            """
            cursor.execute(subject_query, tuple(subject_codes))
            subject_map = {str(row['subject_code']).strip(): row for row in cursor.fetchall()}

        # Combine final data
        final_faculty_subjects = [
            {
                "faculty_id": entry["faculty_id"],
                "faculty_name": faculty_map.get(entry["faculty_id"], "Unknown"),
                "subject_code": entry["subject_code"],
                "subject_name": subject_map.get(entry["subject_code"], {}).get("subject_name", "Unknown"),
                "credits": subject_map.get(entry["subject_code"], {}).get("credits", "N/A"),
                "elective": subject_map.get(entry["subject_code"], {}).get("elective", "N/A"),
                "year": passed_out_year,
                "section": student_section
            }
            for entry in faculty_subjects
        ]

        return render_template("student_subjects.html", faculty_subjects=final_faculty_subjects)

    except Exception as e:
        app.logger.error(f"Error fetching student subjects: {e}")
        return "An error occurred.", 500

    finally:
        cursor.close()
        db.close()


@app.route('/get_passed_out_years')
def get_passed_out_years():
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Get unique passed out years from the profile table
        cursor.execute("SELECT DISTINCT `Passed out year` FROM profile ORDER BY `Passed out year` DESC")
        years = [row['Passed out year'] for row in cursor.fetchall()]
        
        return jsonify(years)
    except Exception as e:
        app.logger.error(f"Error fetching years: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if connection:
            cursor.close()
            connection.close()

@app.route('/get_passed_out_branches/<year>')
def get_passed_out_branches(year):
    try:
        app.logger.info(f"Fetching branches for year: {year}")
        connection = get_db_connection()
        
        if not connection:
            app.logger.error("Database connection failed")
            return jsonify({'error': 'Database connection failed'}), 500
            
        cursor = connection.cursor()
        
        # First, verify if the year exists
        cursor.execute("SELECT COUNT(*) as count FROM profile WHERE `Passed out year` = %s", (year,))
        count = cursor.fetchone()['count']
        app.logger.info(f"Found {count} records for year {year}")
        
        if count == 0:
            return jsonify([])
        
        # Get unique branches for the selected year
        query = """
            SELECT DISTINCT Branch 
            FROM profile 
            WHERE `Passed out year` = %s 
            AND Branch IS NOT NULL 
            AND Branch != ''
            ORDER BY Branch
        """
        app.logger.info(f"Executing query: {query} with year: {year}")
        
        cursor.execute(query, (year,))
        branches = [row['Branch'] for row in cursor.fetchall()]
        
        app.logger.info(f"Found branches: {branches}")
        
        return jsonify(branches)
        
    except Exception as e:
        app.logger.error(f"Error in get_passed_out_branches: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500
        
    finally:
        if 'connection' in locals() and connection:
            cursor.close()
            connection.close()
            app.logger.info("Database connection closed")

@app.route('/get_passed_out_sections/<year>/<branch>')
def get_passed_out_sections(year, branch):
    try:
        app.logger.info(f"Fetching sections for year: {year} and branch: {branch}")
        connection = get_db_connection()
        
        if not connection:
            app.logger.error("Database connection failed")
            return jsonify({'error': 'Database connection failed'}), 500
            
        cursor = connection.cursor()
        
        # Get unique sections for the selected year and branch
        query = """
            SELECT DISTINCT `Section` 
            FROM `profile` 
            WHERE `Passed out year` = %s 
            AND `Branch` = %s 
            AND `Section` IS NOT NULL 
            AND `Section` != ''
            ORDER BY `Section`
        """
        
        cursor.execute(query, (str(year), branch))
        sections = [row['Section'] for row in cursor.fetchall()]
        
        app.logger.info(f"Found sections: {sections}")
        return jsonify(sections)
        
    except Exception as e:
        app.logger.error(f"Error in get_passed_out_sections: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500
        
    finally:
        if 'connection' in locals() and connection:
            cursor.close()
            connection.close()

@app.route('/download_profile', methods=['POST'])
def download_profile():
    try:
        year = request.form.get('passed_out_year')
        branch = request.form.get('branch')
        section = request.form.get('section')
        active_tab = 'download_profile'
        
        # Check for required fields
        if not all([year, branch]):
            error_admin_profile = "Please select Year and Branch"
            if 'super_admin' in session.get('roles', []):
                return render_template(
                    'admin_student.html',
                    active_tab=active_tab,
                    error_admin_profile=error_admin_profile
                )
            elif 'e-admin' in session.get('roles', []):
                return render_template(
                    'e_admin.html',
                    active_tab=active_tab,
                    error_admin_profile=error_admin_profile
                )
            
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Build the query based on the selected filters
        query = """
            SELECT * FROM profile 
            WHERE `Passed out year` = %s 
            AND Branch = %s
        """
        params = [year, branch]
        
        if section and section != 'ALL':
            query += " AND Section = %s"
            params.append(section)
            
        cursor.execute(query, params)
        profiles = cursor.fetchall()
        
        if not profiles:
            error_admin_profile = "No profiles found for the selected criteria"
            if 'super_admin' in session.get('roles', []):
                return render_template(
                    'admin_student.html',
                    active_tab=active_tab,
                    error_admin_profile=error_admin_profile
                )
            elif 'e-admin' in session.get('roles', []):
                return render_template(
                    'e_admin.html',
                    active_tab=active_tab,
                    error_admin_profile=error_admin_profile
                )
        
        # Create Excel file
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()
        
        # Add headers with formatting
        header_format = workbook.add_format({
            'bold': True,
            'align': 'center',
            'bg_color': '#4F81BD',
            'font_color': 'white',
            'border': 1
        })
        
        headers = list(profiles[0].keys())
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)
        
        # Write data with formatting
        data_format = workbook.add_format({
            'align': 'left',
            'border': 1
        })
        
        for row, profile in enumerate(profiles, 1):
            for col, header in enumerate(headers):
                worksheet.write(row, col, profile[header], data_format)
        
        workbook.close()
        output.seek(0)
        
        section_text = section if section != 'ALL' else 'AllSections'
        filename = f'Student_Profiles_{year}_{branch}_{section_text}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        app.logger.error(f"Error downloading profiles: {str(e)}")
        error_admin_profile = f'Error downloading profiles: {str(e)}'
        if 'super_admin' in session.get('roles', []):
            return render_template(
                'admin_student.html',
                active_tab=active_tab,
                error_admin_profile=error_admin_profile
            )
        elif 'e-admin' in session.get('roles', []):
            return render_template(
                'e_admin.html',
                active_tab=active_tab,
                error_admin_profile=error_admin_profile
            )
        
    finally:
        if 'connection' in locals() and connection:
            cursor.close()
            connection.close()

@app.route('/display_subjects')
def display_subjects():
    if 'roles' not in session or 'hod' not in session['roles']:
        return redirect(url_for('signin'))
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Fetch subjects with department names and ids
        cursor.execute("""
            SELECT s.subject_name, s.subject_code, d.department_id, d.department_name, s.semester, s.credits
            FROM subject s
            JOIN department d ON s.department_id = d.department_id
            ORDER BY s.semester, s.subject_name
        """)
        
        subjects = cursor.fetchall()

        # Fetch unique departments for the filter dropdown
        cursor.execute("SELECT department_id, department_name FROM department")
        departments = cursor.fetchall()

        return render_template('display_subjects.html', subjects=subjects, departments=departments)
        
    except Exception as e:
        app.logger.error(f"Error in display_subjects: {str(e)}")
        return render_template('display_subjects.html', subjects=[], error="An error occurred while fetching subjects")
        
    finally:
        if 'connection' in locals() and connection:
            cursor.close()
            connection.close()





@app.route('/download_electives', methods=['POST'])
def download_electives():
    try:
        year = request.form.get('passed_out_year')
        branch = request.form.get('branch')
        section = request.form.get('section')
        active_tab = 'download_electives'

        if not all([year, branch]):
            error_admin_electives = "Please select Year and Branch"
            if 'e-admin' in session.get('roles', []):
                return render_template(
                'e_admin.html',
                active_tab=active_tab,
                error_admin_electives=error_admin_electives
            )
            elif 'hod' in session.get('roles', []):
                return render_template(
                'hod.html',
                active_tab=active_tab,
                error_admin_electives=error_admin_electives
            )   
        connection = get_db_connection()
        cursor = connection.cursor()

        # ✅ JOIN `student_electives` with `profile` AND `subject` to get subject_name
        query = """
            SELECT 
                student_electives.roll_number, 
                profile.`STUDENT NAME` AS student_name, 
                subject.subject_name
            FROM student_electives 
            JOIN profile ON student_electives.roll_number = profile.roll_number 
            JOIN subject ON student_electives.subject_code = subject.subject_code
            WHERE profile.Status = 'active'
            AND profile.`Passed out year` = %s
            AND profile.Branch = %s
        """
        params = [year, branch]

        if section and section != 'ALL':
            query += " AND profile.Section = %s"
            params.append(section)

        cursor.execute(query, params)
        electives = cursor.fetchall()

        if not electives:
            if 'e-admin' in session.get('roles', []):
                return render_template(
                'e_admin.html',
                active_tab=active_tab,
                error_admin_electives="No elective data found."
            )
            elif 'hod' in session.get('roles', []):
                return render_template(
                'hod.html',
                active_tab=active_tab,
                error_admin_electives="No elective data found."
            )   

        # Create Excel file
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()

        # Headers
        headers = ["Roll Number", "Student Name", "Subject Name"]
        for col, header in enumerate(headers):
            worksheet.write(0, col, header)

        # Write Data
        for row, elective in enumerate(electives, 1):
            worksheet.write(row, 0, elective["roll_number"])
            worksheet.write(row, 1, elective["student_name"])
            worksheet.write(row, 2, elective["subject_name"])

        workbook.close()
        output.seek(0)

        filename = f'Student_Electives_{year}_{branch}_{section}.xlsx'
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=filename)

    except Exception as e:
        app.logger.error(f"Error downloading electives: {str(e)}")
        if 'e-admin' in session.get('roles', []):
                return render_template(
                'e_admin.html',
                active_tab=active_tab,
                error_admin_electives=f'Error: {str(e)}'
            )
        elif 'hod' in session.get('roles', []):
                return render_template(
                'hod.html',
                active_tab=active_tab,
                error_admin_electives=f'Error: {str(e)}'
            )   

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'connection' in locals():
            connection.close()


@app.route('/download_Failed_list', methods=['POST'])
def download_failed_list():
    passed_out_year = request.form.get('passed_out_year')
    branch = request.form.get('branch')
    section = request.form.get('section')

    if not (passed_out_year and branch and section):
        return "Missing required inputs", 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch roll numbers and student names
    cursor.execute(
        "SELECT roll_number, `STUDENT NAME` FROM profile WHERE Branch = %s AND Section = %s AND `Passed out year` = %s",
        (branch, section, passed_out_year)
    )
    students = cursor.fetchall()

    if not students:
        return "No students found for the given criteria.", 404

    # Prepare the data structure for the Excel file
    data = []

    for student in students:
        roll_number = student['roll_number']
        student_name = student['STUDENT NAME']

        student_data = {
            'Roll Number': roll_number,
            'Student Name': student_name
        }

        for sem in range(1, 9):  # Loop from sem1 to sem8
            table_name = f"sem{sem}"
            cursor.execute(
                f"SELECT subject_name FROM {table_name} WHERE roll_number = %s AND grade_point = 0 AND grade_secured = 'F'", 
                (roll_number,)
            )
            failed_subjects = [row['subject_name'] for row in cursor.fetchall()]

            if failed_subjects:
                student_data[f'Sem {sem}'] = f"{len(failed_subjects)}({', '.join(failed_subjects)})"
            else:
                student_data[f'Sem {sem}'] = "0"

        data.append(student_data)

    cursor.close()
    conn.close()

    # Column order
    columns = ["Roll Number", "Student Name"] + [f"Sem {i}" for i in range(1, 9)]
    
    # Convert data into a pandas DataFrame
    df = pd.DataFrame(data, columns=columns)

    # Save to Excel
    filename = "failed_students.xlsx"
    df.to_excel(filename, index=False)

    # Send the file as a response
    return send_file(filename, as_attachment=True)

@app.route('/view_failed_list')
def view_failed_list():
    passed_out_year = request.args.get('passed_out_year')
    branch = request.args.get('branch')
    section = request.args.get('section')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Base query with filters
    query = """
        SELECT roll_number, `STUDENT NAME` 
        FROM profile 
        WHERE 1=1
    """
    params = []

    if passed_out_year:
        query += " AND `Passed out year` = %s"
        params.append(passed_out_year)
    if branch:
        query += " AND Branch = %s"
        params.append(branch)
    if section and section != 'ALL':
        query += " AND Section = %s"
        params.append(section)

    cursor.execute(query, params)
    students = cursor.fetchall()

    failed_data = []

    for student in students:
        roll_number = student['roll_number']
        student_name = student['STUDENT NAME']

        student_data = {
            'roll_number': roll_number,
            'student_name': student_name
        }

        for sem in range(1, 9):
            table_name = f"sem{sem}"
            cursor.execute(
                f"SELECT subject_name FROM {table_name} WHERE roll_number = %s AND grade_point = 0 AND grade_secured = 'F'",
                (roll_number,)
            )
            failed_subjects = [row['subject_name'] for row in cursor.fetchall()]

            if failed_subjects:
                student_data[f'sem{sem}'] = f"{len(failed_subjects)}({', '.join(failed_subjects)})"
            else:
                student_data[f'sem{sem}'] = "0"

        failed_data.append(student_data)

    cursor.close()
    conn.close()

    return render_template('view_failed_list.html', failed_data=failed_data)


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)           