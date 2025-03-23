from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from utils.json_utils import load_json
from deepdiff import DeepDiff
import os
import time
import json
import shutil

def go_to_grades(driver):
    try:
        wait = WebDriverWait(driver, 10)

        # Click burger menu and wait
        burger_menu = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[data-widget='pushmenu']")))
        burger_menu.click()
        print("Burger menu clicked.")
        time.sleep(2)

        # Navigate to the grades section.
        lesson_menu = driver.execute_script("""
            const menuItems = document.querySelectorAll('.nav-item.has-treeview');
            for (const item of menuItems) {
                if (item.querySelector('p').textContent.trim().includes('Ders ve Dönem İşlemleri')) {
                    item.classList.add('menu-open');
                    item.querySelector('.nav-link').click();
                    return true;
                }
            }
            return false;
        """)

        if lesson_menu:
            print("Navigation successful.")
            time.sleep(2)

            # Find and click to grades list
            driver.execute_script("""
                const links = document.querySelectorAll('.nav-treeview .nav-item .nav-link');
                for (const link of links) {
                    if (link.textContent.trim().includes('Not Listesi')) {
                        link.click();
                        return true;
                    }
                }
                return false;
            """)
            print("Clicked grades list.")

            # Wait for page load
            iframe = wait.until(EC.presence_of_element_located((By.ID, "IFRAME1")))
            driver.switch_to.frame(iframe)
            time.sleep(3)
            return True
        
        return False
    
    except Exception as e:
        print(f"Navigation Error: {e}")
        return False
    
def get_grades(driver, user, student_id, current_dir):
    # Attempt to navigation
    navigate = go_to_grades(driver)

    if navigate:
        print("Navigation successful.")
    else:
        print("Navigation failed.")
        return False

    try:
        wait = WebDriverWait(driver, 10)
        print("Starting grade scraping...")

        # Wait for animations
        time.sleep(2)
        wait.until(lambda d: d.execute_script('return jQuery.active == 0'))

        # Try to get grades
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
                
                # Save grades to JSON.
                if os.path.exists(data_path):
                    with open(temp_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=4)
                else:    
                    with open(data_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=4)

                # Compare grade files.
                if os.path.exists(temp_path):
                    old_data = load_json(data_path)
                    new_data = load_json(temp_path)
                    diff = DeepDiff(old_data, new_data)

                    # Switch files on change.
                    if diff:
                        shutil.move(temp_path, data_path)
                        return diff
                    
                    # Remove the temp file if no changes.
                    os.remove(temp_path)

                print("Grades successfully saved.")   
                return True

        print("Failed to fetch grades after multiple attempts.")
        return False

    except Exception as e:
        print(f"Data fetch error: {e}")
        return False
