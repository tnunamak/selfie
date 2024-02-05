import logging
import os
import uvicorn
from selfie.api import app
import webbrowser

# Setup logging
logging.basicConfig(filename='app.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

@app.on_event("startup")
def open_browser():
    # Ensure the log file can be opened in append mode without issues
    with open('app.log', 'a') as log_file:
        log_file.write("Application startup, opening browser\n")
    webbrowser.open("http://localhost:8181")

# Configure Uvicorn to use the logging setup
if __name__ == "__main__":
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Adjust Uvicorn logging for PyInstaller
        uvicorn.run("selfie.api:app", host="0.0.0.0", port=8181, log_config=None)
    else:
        # Normal execution
        uvicorn.run("selfie.api:app", host="0.0.0.0", port=8181, reload=True)
