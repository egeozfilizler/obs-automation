from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
import base64
import capsolver

def solve_captcha(driver, captcha_path):
    # Get captcha image
    wait = WebDriverWait(driver, 10)
    captcha_img = wait.until(EC.presence_of_element_located((By.ID, 'imgCaptchaImg')))
    captcha_img.screenshot(captcha_path)

    # Solve captcha problem
    with open(captcha_path, "rb") as f:
        b64_img = base64.b64encode(f.read()).decode('utf-8')

    captcha_result = capsolver.solve({
        "type": "ImageToTextTask",
        "module": "common",
        "body": b64_img
    })

    result_text = captcha_result["text"]
    numbers = list(map(int, re.findall(r'\d+', result_text)))
    return str(sum(numbers))