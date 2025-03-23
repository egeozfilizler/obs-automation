import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json

def send_notification(data_path, student_id, diff, sender_email, sender_password):
    """
    Extracts only 'grade' changes from a DeepDiff result and sends an email notification.

    Parameters:
        diff (dict): The DeepDiff result containing grade changes.
        student_id (str): The student's ID.
        sender_email (str): Sender's email address.
        sender_password (str): Sender's email password.
    """
    changes = []

    # Load grades data
    with open(data_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
        grades = data.get("grades", [])

    # Process only grade changes
    if "values_changed" in diff:
        for key, change in diff["values_changed"].items():
            if "grade" in key:  # Only process grade changes
                new_value = change.get("new_value")
                old_value = change.get("old_value")
                course_index = int(key.split("[")[2].split("]")[0])  # Extract course index
                course = grades[course_index]
                course_code = course.get("code")
                course_name = course.get("name")

                changes.append(f"{course_code} - {course_name}: Not değişti → '{old_value}' → '{new_value}'")

    # If no grade changes, do not send an email
    if not changes:
        print("Not değişikliği bulunamadı. E-posta gönderilmeyecek.")
        return False

    # Format email content
    receiver_email = f"{student_id}@dogus.edu.tr"
    subject = f"{student_id} - Not Güncellemesi"
    body = "Merhaba,\n\nAşağıdaki derslerin notları güncellendi:\n\n" + "\n".join(changes) + "\n\nİyi günler."

    # Create email message
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = receiver_email

    # Attach the body with UTF-8 encoding
    msg.attach(MIMEText(body, "plain", "utf-8"))

    # Send email via SMTP
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()  # Secure the connection
            server.login(sender_email, sender_password)  # Log in
            server.sendmail(sender_email, receiver_email, msg.as_string())  # Send email
        print(f"E-posta başarıyla gönderildi: {receiver_email}")
        return True
    except Exception as e:
        print(f"Hata: E-posta gönderilemedi! {e}")
        return False
