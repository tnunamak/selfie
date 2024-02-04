import uvicorn
import webbrowser
from selfie.api import app


@app.on_event("startup")
def open_browser():
    webbrowser.open("http://localhost:8181")


# Uncomment this for hot-reloading
uvicorn.run("selfie.api:app", host="0.0.0.0", port=8181, reload=True)
# uvicorn.run(app, host="0.0.0.0", port=8181)
