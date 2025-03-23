import time
from main import main

def run_scheduler():
    while True:
        print("Running the main process...")
        try:
            main()  # Call the main function from main.py
        except Exception as e:
            print(f"Error occurred while running the main process: {e}")
        
        print("Waiting for 30 minutes before the next run...")
        time.sleep(30 * 60)  # Wait for 30 minutes (30 minutes * 60 seconds)

if __name__ == "__main__":
    print("Press Ctrl+C to stop")
    try:
        run_scheduler()
    except KeyboardInterrupt:
        print("\nGrade checker stopped by user")