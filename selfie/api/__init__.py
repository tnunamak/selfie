import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
import logging

from selfie.api.completions import router as completions_router
from selfie.api.data_sources import router as data_sources_router
from selfie.api.documents import router as documents_router
from selfie.api.index_documents import router as index_documents_router
from selfie.api.models import router as models_router

logger = logging.getLogger(__name__)


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

current_file_dir = os.path.dirname(os.path.realpath(__file__))
static_files_dir = os.path.join(current_file_dir, "../web")

app.mount("/static", StaticFiles(directory=static_files_dir), name="static")


app.include_router(completions_router)
app.include_router(data_sources_router)
app.include_router(documents_router)
app.include_router(index_documents_router)
app.include_router(models_router)


@app.get("/", response_class=HTMLResponse)
async def serve_index_html():
    # Construct the full path to 'index.html'
    index_html_path = os.path.join(static_files_dir, "index.html")
    with open(index_html_path, "r") as f:
        return HTMLResponse(content=f.read())
