import requests
from bs4 import BeautifulSoup
import pymysql
import pandas as pd
import re

# Define a mapping from grade to grade points
grade_to_points = {
    'S': 10,
    'A': 9,
    'B': 8,
    'C': 7,
    'D': 6,
    'E': 5,
    'F': 0
}


def get_result_page(url, roll_number, session):
    data = {
        "htno": str(roll_number),
        "mbstatus": "SEARCH",
        "Submit": "Go"
    }
    response = session.post(url, data=data)
    if response.status_code == 200:
        return response.text
    else:
        return None


def extract_details(html_content, roll_number, subject_code_start, subject_code_end, letter_range):
    soup = BeautifulSoup(html_content, 'html.parser')
    details = {f"Semester{i}": [] for i in range(1, 9)}

    # Regex pattern to match subject codes
    code_pattern = rf"^(\d{{3,4}})([A-Za-z]+)?$"

    marks_table = soup.find('table', {'id': 'AutoNumber4'})
    sgpa_data = {}  # Dictionary to store SGPA data for each semester

    # Extract SGPA data from the page
    sgpa_table = soup.find_all('tr')
    for row in sgpa_table:
        cells = row.find_all('td')

        # Handle both cases for SGPA extraction
        if len(cells) >= 2:  # Ensure there are enough columns
            # Case 1: Semester in 0th col
            semester_text = cells[0].text.strip()
            result_with_sgpa = cells[1].text.strip() if len(cells) > 1 else ""

            if semester_text[0].isdigit():  # Valid semester
                semester = int(semester_text[0])
                sgpa = result_with_sgpa.split()[-1]  # Extract SGPA value
                sgpa_data[semester] = sgpa  # Store SGPA for the semester

        if len(cells) >= 3:  # Case 2: Semester in 1st col, SGPA in 2nd col
            semester_text = cells[1].text.strip()
            result_with_sgpa = cells[2].text.strip() if len(cells) > 2 else ""

            if semester_text[0].isdigit():  # Valid semester
                semester = int(semester_text[0])
                sgpa = result_with_sgpa.split()[-1]  # Extract SGPA value
                sgpa_data[semester] = sgpa  # Store SGPA for the semester

    # Extract the subject details from the marks table
    if marks_table:
        for row in marks_table.find_all('tr')[1:]:  # Skip header rows
            cells = row.find_all('td')
            if len(cells) > 3:
                sub_code = cells[0].text.strip()

                # Validate subject codes
                match = re.match(code_pattern, sub_code)
                if match:
                    subject_code_valid = False
                    numeric_part = match.group(1)
                    letter_part = match.group(2) if match.group(2) else ""

                    if numeric_part.isdigit():
                        numeric_part = int(numeric_part)
                        if subject_code_start <= numeric_part <= subject_code_end:
                            subject_code_valid = True
                    elif letter_part.isalpha():
                        subject_code_valid = True

                    if subject_code_valid:
                        subject_name = cells[1].text.strip()
                        credits = cells[2].text.strip()
                        grade_secured = cells[4].text.strip() if len(
                            cells) > 4 else cells[3].text.strip()

                        # Determine semester based on subject code
                        semester = f"Semester{int(sub_code[0])}" if sub_code[0].isdigit(
                        ) and 1 <= int(sub_code[0]) <= 8 else None
                        if semester:
                            subject_data = {
                                "Roll Number": roll_number,
                                "Subject Code": sub_code,
                                "Subject Name": subject_name,
                                "Credits": credits,
                                "Grade Secured": grade_secured,
                                "Grade Point": grade_to_points.get(grade_secured, 0)
                            }
                            details[semester].append(subject_data)

    return details, sgpa_data


def scrape_ou_results(url, roll_numbers, subject_code_start, subject_code_end, letter_range):
    all_results = {f"Semester{i}": [] for i in range(1, 9)}
    session = requests.Session()
    session.get(url)

    for roll_number in roll_numbers:
        html_content = get_result_page(url, roll_number, session)
        if html_content:
            details, sgpa_data = extract_details(
                html_content, roll_number, subject_code_start, subject_code_end, letter_range
            )

            # Store data without overwriting for each roll number
            for semester, subjects in details.items():
                for subject in subjects:
                    # Add SGPA to each subject
                    subject['SGPA'] = sgpa_data.get(int(semester[-1]), "")
                    subject['Roll Number'] = roll_number
                    all_results[semester].append(subject)

    return all_results


def determine_semester(subject_code):
    # Assuming subject codes start with the semester number
    if subject_code and subject_code[0].isdigit():
        return int(subject_code[0])
    return None


def store_results_in_db(results):
    # Connect to the MySQL database
    connection = pymysql.connect(
        host='localhost',
        user='root',
        password='ammu2007',  # Update with your actual password
        database='user_management'
    )

    try:
        with connection.cursor() as cursor:
            for result in results:
                # Extract result for debugging
                roll_number = result.get('roll_number')
                passed_out_year = result.get('passed_out_year')
                subject_code = result.get('subject_code')
                subject_name = result.get('subject_name')
                credits = result.get('credits')
                grade_secured = result.get('grade_secured')
                grade_point = result.get('grade_point')
                exam_series = result.get('exam_series')  # Fetch exam series

                # Log inputs for debugging
                # print(
                #     f"Processing roll_number: {roll_number}, subject_code: {subject_code}, exam_series: {exam_series}")
                if grade_secured.strip().lower() == 'ab':  # Case-insensitive check for 'AB'
                    grade_secured = 'AB'
                    exam_series = 'Supply'
                # Determine semester based on subject code
                semester = determine_semester(subject_code)
                if semester is None:
                    continue  # Skip if semester cannot be determined

                # Insert or update data in the appropriate semester table
                table_name = f"sem{semester}"
                select_sql = f"""
                SELECT id, grade_secured, exam_series FROM {table_name}
WHERE roll_number = %s AND subject_code = %s 
"""
                cursor.execute(select_sql, (roll_number, subject_code))
                record = cursor.fetchone()

                # print(f"Fetched record: {record}")  # Log fetched record

                if record:
                    # Fetch existing exam_series
                    current_exam_series = record[2]
                    # print(
                    #     f"Current exam_series in database: {current_exam_series}")

                    # Allow updates if new exam_series is 'Revaluation' or current is 'Regular'
                    if exam_series == 'Revaluation' or current_exam_series == 'Regular':
                        # print(
                        #     f"Updating record: {subject_code}, exam_series: {exam_series}")
                        update_sql = f"""
                        UPDATE {table_name}
                        SET subject_name = %s, credits = %s, grade_secured = %s, grade_point = %s, exam_series = %s
                        WHERE id = %s
                        """
                        cursor.execute(update_sql, (subject_name, credits,
                                                    grade_secured, grade_point, exam_series, record[0]))
                    # else:
                    #     print(
                    #         f"Skipping update for {subject_code} as the new exam_series '{exam_series}' cannot replace the current '{current_exam_series}'.")

                else:
                    # Insert new record only if exam_series is 'Regular'
                    if exam_series == 'Regular' or (exam_series == 'Supply' and grade_secured == 'AB'):
                        # print(
                        #     f"Inserting new record for {subject_code}, exam_series: {exam_series}")

                        insert_sql = f"""
                        INSERT INTO {table_name} (passed_out_year, roll_number, subject_code, subject_name, credits, grade_secured, grade_point, exam_series)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """
                        cursor.execute(insert_sql, (passed_out_year, roll_number, subject_code,
                                                    subject_name, credits, grade_secured, grade_point, exam_series))

            # Commit all changes after processing all results
            connection.commit()
            print("All changes committed successfully.")
    except Exception as e:
        print(f"An error occurred: {e}")
        connection.rollback()  # Roll back in case of error
    finally:
        connection.close()
