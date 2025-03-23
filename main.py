from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from credentials import users, CAPSOLVER_API_KEY, SENDER_MAIL, SENDER_PASSWORD
from auth import login_to_obs
from grades_monitor import get_grades
from notifier import send_notification
import os
import sys
import time
import capsolver
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure UTF-8 output for Windows systems
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Set Capsolver API key
capsolver.api_key = CAPSOLVER_API_KEY

# File Paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
CAPTCHA_IMAGE_PATH = os.path.join(CURRENT_DIR, "temp/captcha.png")

# Create folders
os.makedirs(os.path.join(CURRENT_DIR, "temp"), exist_ok=True)
os.makedirs(os.path.join(CURRENT_DIR, "data"), exist_ok=True)

# Initialize the Selenium WebDriver
def start_browser():
    options = webdriver.ChromeOptions()
    options.add_experimental_option("detach", True)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    driver.execute_cdp_cmd("Page.enable", {})
    driver.execute_cdp_cmd("Page.setWebLifecycleState", {"state": "active"})

    return driver

# Function to process a single user's operations
def process_user(user, user_data):
    try:
        driver = start_browser()
        driver.get("https://obs.dogus.edu.tr/oibs/std/login.aspx")
        print(f"{user}: Opened OBS login page.")

        data_path = os.path.join(CURRENT_DIR, f"data/{user}_grades.json")

        for _ in range(3):
            account = login_to_obs(driver, user_data, CAPTCHA_IMAGE_PATH)
            if account:
                print(f"{user}: Login successful.")
                break
            else:
                print(f"{user}: Login failed. Retrying...")

        fetch = get_grades(driver, user, account, CURRENT_DIR)
        if fetch:
            print(f"{user}: Fetch successful.")
        else:
            print(f"{user}: Fetch failed.")

        if isinstance(fetch, dict):
            mail = send_notification(data_path, account, fetch, SENDER_MAIL, SENDER_PASSWORD)
            if mail:
                print(f"{user}: Email sent.")
            else:
                print(f"{user}: Notification failed.")

    except Exception as e:
        print(f"{user}: Error - {str(e)}")
    finally:
        driver.quit()
        print(f"{user}: Browser closed.")

# Main process
def main():
    max_workers = min(2, len(users))  # Limit to a maximum of 2 threads at the same time (too many threads may consume excessive RAM)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_user, user, user_data): user for user, user_data in users.items()}

        for future in as_completed(futures):
            user = futures[future]
            try:
                future.result()  # Catch any errors that occur
            except Exception as e:
                print(f"{user}: Task failed with error: {e}")

if __name__ == "__main__":
    main()
