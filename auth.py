from captcha import solve_captcha
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def login_to_obs(driver, user_credentials, captcha_path):
    # Get user credentials
    id = user_credentials["id"]
    password = user_credentials["password"]

    # Get the captcha result
    captcha = solve_captcha(driver, captcha_path)

    try:
        wait = WebDriverWait(driver, 10)

        # Wait until the inputs appear
        id_input = wait.until(EC.presence_of_element_located((By.ID, 'txtParamT01')))
        password_input = wait.until(EC.presence_of_element_located((By.ID, 'txtParamT02')))
        captcha_input = wait.until(EC.presence_of_element_located((By.ID, 'txtSecCode')))
        
        # Clear fields
        id_input.clear()
        password_input.clear()
        captcha_input.clear()

        # Fill the inputs
        driver.execute_script("arguments[0].value = arguments[1];", id_input, id)
        driver.execute_script("arguments[0].value = arguments[1];", password_input, password)
        driver.execute_script("arguments[0].value = arguments[1];", captcha_input, captcha)

        # Submit infos
        driver.execute_script(
            """
            document.getElementById('btnLogin').click();
            return true;
            """
        )

        # Wait for login to complete
        time.sleep(3)

         # Verify login success
        if 'index.aspx' in driver.current_url:
            print("Login successful")
            return id
            
        print(f"Login might have failed. Current URL: {driver.current_url}")
        return False

    except Exception as e:
        print(f"Login error: {e}")
        return False