"""
Consolidated main script combining login, captcha solve, grade scraping,
notification and orchestration logic in a single file.

Note: This file expects `credentials.py` to remain in the project root and
imports secrets from it.
"""

import os
import sys
import time
import json
import shutil
import re
import base64
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import psutil
import capsolver
from deepdiff import DeepDiff

import logging
from apscheduler.schedulers.blocking import BlockingScheduler

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
	InvalidElementStateException,
	ElementNotInteractableException,
	StaleElementReferenceException,
	ElementClickInterceptedException,
	TimeoutException,
)

from webdriver_manager.chrome import ChromeDriverManager

# Import credentials from separate file (kept intentionally separate)
from credentials import (
	users,
	CAPSOLVER_API_KEY,
	SENDER_MAIL,
	SENDER_PASSWORD,
)

# Path helpers
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
CAPTCHA_IMAGE_PATH = os.path.join(CURRENT_DIR, "temp", "captcha.png")
# Optional path to a system-installed chromedriver (useful on Linux)
DRIVER_PATH = '/usr/bin/chromedriver'

# Configure logging
logging.basicConfig()
logging.getLogger('apscheduler').setLevel(logging.INFO)

# Ensure folders exist
os.makedirs(os.path.join(CURRENT_DIR, "temp"), exist_ok=True)
os.makedirs(os.path.join(CURRENT_DIR, "data"), exist_ok=True)

# Configure UTF-8 output for Windows
if sys.platform.startswith('win'):
	try:
		sys.stdout.reconfigure(encoding='utf-8')
	except Exception:
		pass

# Configure capsolver key
capsolver.api_key = CAPSOLVER_API_KEY


def load_json(file_path):
	"""Small helper to load JSON or return None if missing."""
	if os.path.exists(file_path):
		with open(file_path, 'r', encoding='utf-8') as f:
			return json.load(f)
	return None


def solve_captcha(driver, captcha_path):
	"""Save captcha image element to file and solve via capsolver."""
	wait = WebDriverWait(driver, 10)
	captcha_img = wait.until(EC.presence_of_element_located((By.ID, 'imgCaptchaImg')))
	captcha_img.screenshot(captcha_path)

	with open(captcha_path, 'rb') as f:
		b64_img = base64.b64encode(f.read()).decode('utf-8')

	captcha_result = capsolver.solve({
		"type": "ImageToTextTask",
		"module": "common",
		"body": b64_img,
	})

	result_text = captcha_result.get('text', '')
	numbers = list(map(int, re.findall(r'\d+', result_text)))
	return str(sum(numbers)) if numbers else result_text


def safe_click(driver, element, timeout=5):
	"""Robust click helper: tries element.click(), scroll, JS click, and
	hides common overlays when click is intercepted.

	Raises the last exception if all attempts fail.
	"""
	end_time = time.time() + timeout
	last_exc = None
	while time.time() < end_time:
		try:
			element.click()
			return True
		except (ElementClickInterceptedException, ElementNotInteractableException, InvalidElementStateException) as e:
			last_exc = e
			# try scroll into view
			try:
				driver.execute_script('arguments[0].scrollIntoView({block: "center", inline: "center"});', element)
				time.sleep(0.1)
				element.click()
				return True
			except Exception:
				pass
			# try JS click
			try:
				driver.execute_script('arguments[0].click();', element)
				return True
			except Exception:
				pass
				# try hiding common overlays then retry
				try:
					driver.execute_script("""
					const selectors = ['[class*="overlay"]', '.modal', '.swal2-container', '.fancybox-overlay', '.ui-widget-overlay'];
					for (const s of selectors) {
						for (const el of document.querySelectorAll(s)) {
							el.style.display = 'none';
						}
					}
					""")
					time.sleep(0.08)
					try:
						element.click()
						return True
					except Exception:
						pass
				except Exception:
					# ignore errors while attempting to hide overlays
					pass
				time.sleep(0.12)
	# all retries failed
	raise last_exc if last_exc is not None else Exception('click failed')


def login_to_obs(driver, wait, user_credentials, captcha_path):
	"""Perform login to OBS using credentials and captcha solver.

	Returns the student id (account) on success or False on failure.
	"""
	user_id = user_credentials['id']
	password = user_credentials['password']

	try:
		wait.until(EC.presence_of_element_located((By.ID, 'txtParamT01')))
		captcha = solve_captcha(driver, captcha_path)
		if not captcha:
			print("CAPTCHA çözülemedi.")
			return False

		def _type_and_verify(element, text, timeout=5):
			try:
				element.clear()
			except Exception:
				pass

			try:
				# send the whole text at once instead of character-by-character to avoid
				# artificially slow "human-like" typing
				element.send_keys(text)

				end_time = time.time() + timeout
				while time.time() < end_time:
					try:
						val = element.get_attribute('value') or ''
					except StaleElementReferenceException:
						element = driver.find_element(By.ID, element.get_attribute('id'))
						val = element.get_attribute('value') or ''
					if text == val or val.endswith(text) or text in val:
						return True
					time.sleep(0.1)
			except (InvalidElementStateException, ElementNotInteractableException, StaleElementReferenceException):
				pass

			try:
				driver.execute_script(
					"arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input'));",
					element,
					text,
				)
				return True
			except Exception:
				return False

		id_input = wait.until(EC.presence_of_element_located((By.ID, 'txtParamT01')))
		_type_and_verify(id_input, user_id)

		password_input = wait.until(EC.presence_of_element_located((By.ID, 'txtParamT02')))
		_type_and_verify(password_input, password)

		captcha_input = wait.until(EC.presence_of_element_located((By.ID, 'txtSecCode')))
		_type_and_verify(captcha_input, captcha)

		try:
			def _fields_ready(driver_):
				try:
					v1 = driver_.find_element(By.ID, 'txtParamT01').get_attribute('value') or ''
					v2 = driver_.find_element(By.ID, 'txtParamT02').get_attribute('value') or ''
					v3 = driver_.find_element(By.ID, 'txtSecCode').get_attribute('value') or ''
					return (user_id in v1) and (password in v2) and (captcha in v3)
				except Exception:
					return False

			WebDriverWait(driver, 7).until(_fields_ready)
		except TimeoutException:
			print("Uyarı: bazı alanlar beklenen değeri içermiyor, yine de gönderilecek.")

		login_button = wait.until(EC.presence_of_element_located((By.ID, 'btnLogin')))
		try:
			login_button = wait.until(EC.element_to_be_clickable((By.ID, 'btnLogin')))
			login_button.click()
		except Exception:
			try:
				ActionChains(driver).move_to_element(login_button).click().perform()
			except Exception:
				try:
					driver.execute_script("arguments[0].click();", login_button)
				except Exception as e:
					print(f"Butona tıklama denemeleri başarısız: {e}")

		time.sleep(3)

		if 'index.aspx' in driver.current_url:
			print("Giriş başarılı (URL doğrulandı).")
			return user_id

		print(f"Giriş başarısız oldu. Güncel URL: {driver.current_url}")
		try:
			error_msg = driver.find_element(By.ID, "lblGvnlk").text
			if error_msg:
				print(f"Hata Mesajı: {error_msg}")
		except Exception:
			pass
		return False

	except Exception as e:
		print(f"Giriş hatası: {e}")
		return False


def go_to_grades(driver):
	try:
		wait = WebDriverWait(driver, 10)

		# Open the side menu (burger)
		burger = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[data-widget='pushmenu']")))
		try:
			safe_click(driver, burger)
		except Exception as e:
			print(f"Could not open main menu: {e}")
			return False

		# small pause for UI animation
		time.sleep(0.6)

		# Click the 'Ders ve Dönem İşlemleri' parent treeview item
		try:
			parent_xpath = "//li[contains(@class,'has-treeview') and .//p[contains(normalize-space(.),'Ders ve Dönem İşlemleri')]]"
			parent = wait.until(EC.presence_of_element_located((By.XPATH, parent_xpath)))
			nav_link = parent.find_element(By.XPATH, ".//a[contains(@class,'nav-link')]")
			safe_click(driver, nav_link)
		except Exception as e:
			print(f"Could not open 'Ders ve Dönem İşlemleri' menu: {e}")

		# wait for submenu to render
		time.sleep(0.8)

		# Click the 'Not Listesi' link
		try:
			not_list_xpath = "//a[contains(normalize-space(.),'Not Listesi')]"
			not_link = wait.until(EC.element_to_be_clickable((By.XPATH, not_list_xpath)))
			safe_click(driver, not_link)
		except Exception as e:
			print(f"Could not click 'Not Listesi' link: {e}")
			return False

		# switch to iframe
		iframe = wait.until(EC.presence_of_element_located((By.ID, "IFRAME1")))
		driver.switch_to.frame(iframe)
		time.sleep(1.8)
		return True

	except Exception as e:
		print(f"Navigation Error: {e}")
		return False


def get_grades(driver, user, student_id, current_dir):
	navigate = go_to_grades(driver)
	if not navigate:
		print("Navigation failed.")
		return False

	try:
		wait = WebDriverWait(driver, 10)
		time.sleep(2)
		wait.until(lambda d: d.execute_script('return jQuery.active == 0'))

		for _ in range(3):
			grades = driver.execute_script("""
				try {
					const table = document.getElementById('grd_not_listesi');
					if (!table) return null;
					return Array.from(table.querySelectorAll('tr')).slice(1).map(row => {
						const cols = row.getElementsByTagName('td');
						return cols.length >= 8 ? {
							'section': cols[0].textContent.trim(),
							'code': cols[1].textContent.trim(),
							'name': cols[2].textContent.trim(),
							'status': cols[3].textContent.trim(),
							'scores_raw': cols[4].textContent.trim(),
							'average': cols[5].textContent.trim(),
							'grade': cols[6].textContent.trim(),
							'result': cols[7].textContent.trim()
						} : null;
					}).filter(Boolean);
				} catch(e) {
					console.error(e);
					return null;
				}
			""")

			if grades:
				data = {"student_id": student_id, "grades": grades}
				data_path = os.path.join(current_dir, f"data/{user}_grades.json")
				temp_path = os.path.join(current_dir, "data/temp_grades.json")

				if os.path.exists(data_path):
					with open(temp_path, 'w', encoding='utf-8') as f:
						json.dump(data, f, ensure_ascii=False, indent=4)
				else:
					with open(data_path, 'w', encoding='utf-8') as f:
						json.dump(data, f, ensure_ascii=False, indent=4)

				if os.path.exists(temp_path):
					old_data = load_json(data_path)
					new_data = load_json(temp_path)
					diff = DeepDiff(old_data, new_data)

					if diff:
						shutil.move(temp_path, data_path)
						return diff

					os.remove(temp_path)

				print("Grades successfully saved.")
				return True

		print("Failed to fetch grades after multiple attempts.")
		return False

	except Exception as e:
		print(f"Data fetch error: {e}")
		return False


def send_notification(data_path, student_id, diff, sender_email, sender_password):
	changes = []

	with open(data_path, 'r', encoding='utf-8') as file:
		data = json.load(file)
		grades = data.get('grades', [])

	if 'values_changed' in diff:
		for key, change in diff['values_changed'].items():
			if 'grade' in key:
				new_value = change.get('new_value')
				old_value = change.get('old_value')
				try:
					course_index = int(key.split('[')[2].split(']')[0])
					course = grades[course_index]
					course_code = course.get('code')
					course_name = course.get('name')
					changes.append(f"{course_code} - {course_name}: Not değişti → '{old_value}' → '{new_value}'")
				except Exception:
					# best-effort formatting if parsing fails
					changes.append(f"Not değişti: {old_value} → {new_value}")

	if not changes:
		print("Not değişikliği bulunamadı. E-posta gönderilmeyecek.")
		return False

	receiver_email = f"{student_id}@dogus.edu.tr"
	subject = f"{student_id} - Not Güncellemesi"
	body = "Merhaba,\n\nAşağıdaki derslerin notları güncellendi:\n\n" + "\n".join(changes) + "\n\nİyi günler."

	msg = MIMEMultipart()
	msg['Subject'] = subject
	msg['From'] = sender_email
	msg['To'] = receiver_email
	msg.attach(MIMEText(body, 'plain', 'utf-8'))

	try:
		with smtplib.SMTP('smtp.gmail.com', 587) as server:
			server.starttls()
			server.login(sender_email, sender_password)
			server.sendmail(sender_email, receiver_email, msg.as_string())
		print(f"E-posta başarıyla gönderildi: {receiver_email}")
		return True
	except Exception as e:
		print(f"Hata: E-posta gönderilemedi! {e}")
		return False


def logout_from_obs(driver):
	"""Attempt to logout by clicking profile photo and logout button.

	This will switch back to the default content (in case we are inside an iframe)
	and then try to click elements with IDs 'imgPhoto' and 'btnLogout' in order.
	"""
	try:
		# Ensure we're not inside an iframe
		try:
			driver.switch_to.default_content()
		except Exception:
			pass

		wait = WebDriverWait(driver, 5)

		try:
			photo = wait.until(EC.element_to_be_clickable((By.ID, 'imgPhoto')))
			try:
				photo.click()
			except Exception:
				try:
					driver.execute_script("arguments[0].click();", photo)
				except Exception:
					pass
			time.sleep(0.5)
		except Exception:
			# If profile photo not found/clickable, continue to try logout button anyway
			pass

		try:
			logout_btn = wait.until(EC.element_to_be_clickable((By.ID, 'btnLogout')))
			try:
				logout_btn.click()
			except Exception:
				try:
					driver.execute_script("arguments[0].click();", logout_btn)
				except Exception:
					pass
			time.sleep(3)
			print('Çıkış işlemi tamamlandı (logout).')
			return True
		except Exception:
			print('Çıkış butonu bulunamadı veya tıklanamadı.')
			return False

	except Exception as e:
		print(f'Çıkış sırasında hata: {e}')
		return False

def connect_driver(headless=False):
	try:
		# Use `options` variable name and avoid relying on a profile path
		options = Options()
		options.add_argument('--no-first-run')
		options.add_argument('--no-default-browser-check')
		options.add_argument('--disable-password-manager-reauthentication')
		options.add_argument('--password-store=basic')
		if headless:
			# headless flag for modern Chrome
			options.add_argument('--headless=new')
			options.add_argument('--disable-gpu')
		# Helpful defaults for Linux environments
		options.add_argument('--no-sandbox')
		options.add_argument('--disable-dev-shm-usage')

		# Prefer a system chromedriver if present (useful for Linux)
		if os.path.exists(DRIVER_PATH):
			service = Service(DRIVER_PATH)
			try:
				driver = webdriver.Chrome(service=service, options=options)
				print(f'Chrome WebDriver başlatıldı (system driver: {DRIVER_PATH}).')
				return driver
			except Exception as e:
				print(f'Failed to start driver at {DRIVER_PATH}: {e} -- falling back to webdriver-manager')

		# Fallback to webdriver-manager
		service = Service(ChromeDriverManager().install())
		# Explicitly create the driver with Service and options as requested
		driver = webdriver.Chrome(service=service, options=options)
		print('Chrome WebDriver başlatıldı (webdriver-manager kullanıldı).')
		return driver
	except Exception as e:
		print(f"Chrome WebDriver başlatılırken bir hata oluştu: {e}")
		return None


def terminate_chrome_processes():
	try:
		for proc in psutil.process_iter(['pid', 'name']):
			name = proc.info.get('name') or ''
			if 'chrome' in name.lower():
				try:
					proc.terminate()
				except Exception:
					pass
		print('Chrome işlemleri sonlandırıldı.')
	except Exception as e:
		print(f'Chrome işlemleri sonlandırılırken hata oluştu: {e}')


def process_user(driver, wait, user, user_data):
	try:
		driver.get('https://obs.dogus.edu.tr/oibs/std/login.aspx')

		data_path = os.path.join(CURRENT_DIR, f"data/{user}_grades.json")
		account = None

		for _ in range(3):
			account = login_to_obs(driver, wait, user_data, CAPTCHA_IMAGE_PATH)
			if account:
				break
			driver.get('https://obs.dogus.edu.tr/oibs/std/login.aspx')
			time.sleep(2)

		if not account:
			print(f"{user}: 3 deneme sonunda giriş yapılamadı. Bu kullanıcı atlanıyor.")
			return

		fetch = get_grades(driver, user, account, CURRENT_DIR)

		# After fetching grades (regardless of result), try to logout from OBS UI
		try:
			logout_from_obs(driver)
		except Exception as e:
			print(f"{user}: Çıkış (logout) sırasında hata - {e}")

		if isinstance(fetch, dict):
			mail = send_notification(data_path, account, fetch, SENDER_MAIL, SENDER_PASSWORD)
			if mail:
				print(f"{user}: E-posta gönderildi.")
			else:
				print(f"{user}: Bildirim (e-posta) başarısız oldu.")
		elif fetch is True:
			print(f"{user}: Notlarda değişiklik yok.")
		else:
			print(f"{user}: Not çekme işlemi başarısız oldu.")

	except Exception as e:
		print(f"{user}: İşlem sırasında hata - {str(e)}")

def run_check():
    """
    Bu, sizin orijinal 'main' fonksiyonunuzun içindeki tüm mantıktır.
    İsmini 'main'den 'run_check'e değiştirdik.
    """
    driver = None
    try:
        driver = connect_driver(headless=False)
        if driver is None:
            print('Driver alınamadı, program sonlandırılıyor.')
            terminate_chrome_processes()
            return

        wait = WebDriverWait(driver, 10)

        for user, user_data in users.items():
            print(f"--- İşlem başlıyor: {user} ---")
            process_user(driver, wait, user, user_data)
            print(f"--- İşlem bitti: {user} ---")
            time.sleep(5) # Bu 'time.sleep' kalabilir, kullanıcılar arası beklemeyi sağlar.

        print('Tüm kullanıcılar tamamlandı.')

    except Exception as e:
        print(f"Ana işlem hatası: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        terminate_chrome_processes()
        print('Program oturumu sonlandı.')		


def main():
    scheduler = BlockingScheduler()
    # run_check fonksiyonunu her 15 dakikada bir çalıştır
    scheduler.add_job(run_check, 'interval', minutes=15)
    
    # Zamanlayıcıyı hemen başlatmak için ilk çalışmayı manuel olarak tetikleyebilirsiniz
    print("İlk kontrol hemen başlatılıyor...")
    run_check()
    
    print("Zamanlayıcı başlatıldı. Sonraki kontrol 15 dakika sonra.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Zamanlayıcı durduruldu.")
        pass

if __name__ == '__main__':
    # Bu dosya, tüm mantığı içeren ana script'tir.
    main()
