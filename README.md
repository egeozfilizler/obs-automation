# OBS Automation with Selenium

This project automates the process of logging into the OBS (Online Student Information System), retrieving grades, and sending notifications using Selenium WebDriver.

## Features
- Automated login to OBS using Selenium
- CAPTCHA solving using Capsolver API
- Fetching student grades
- Sending notifications via email
- Parallel execution for multiple users

## Technologies Used
- Python
- Selenium WebDriver
- Capsolver API
- ThreadPoolExecutor (for parallel execution)
- Email SMTP for notifications

## Installation
### Prerequisites
- Python 3.11.0 installed
- Google Chrome installed
- ChromeDriver installed (managed via `webdriver-manager`)

### Install Dependencies
```sh
pip install -r requirements.txt
```

## Configuration
### Environment Variables / Configuration File
Create a `credentials.py` file and define:
```python
users = {
    "user1": {"username": "your_username", "password": "your_password"},
    "user2": {"username": "another_username", "password": "another_password"}
}

CAPSOLVER_API_KEY = "your_capsolver_api_key"
SENDER_MAIL = "your_email@example.com"
SENDER_PASSWORD = "your_email_password"
```

## Usage
### Running the Automation
To execute the script, simply run:
```sh
python main.py
```

### Parallel Execution
The script supports multi-threading with `ThreadPoolExecutor` to process multiple users in parallel, reducing execution time.

## File Structure
```
project-root/
│── credentials.py       # Stores user credentials and API keys
│── auth.py              # Handles OBS login process
│── grades_monitor.py    # Fetches student grades
│── notifier.py          # Sends email notifications
│── main.py              # Main execution file
│── requirements.txt     # Dependencies list
│── temp/                # Temporary storage (e.g., CAPTCHA images)
│── data/                # Stores user grade data
```

## License
This project is licensed under the MIT License.

## Contribution
Feel free to contribute by submitting issues or pull requests.
