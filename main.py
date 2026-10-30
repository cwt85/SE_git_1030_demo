"""Run locally: python -m uvicorn main:app --host 127.0.0.1 --port 8000."""
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError

from DB import DatabaseError
from route.events import router

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app = FastAPI(title="拾光活動報名平台", version="1.0.0")
app.include_router(router, prefix="/api/v1")


@app.exception_handler(DatabaseError)
async def database_rule_error(request: Request, error: DatabaseError):
    return JSONResponse(status_code=error.status_code, content={"detail": str(error)})


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, error: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": "資料格式不正確，請檢查必填欄位、電話與日期時間。"})


@app.exception_handler(SQLAlchemyError)
async def database_connection_error(request: Request, error: SQLAlchemyError):
    # Log only the exception class; SQLAlchemy exceptions may embed submitted data.
    logger.error("Database request failed: %s", type(error).__name__)
    return JSONResponse(status_code=503, content={"detail": "目前無法連線到資料庫，請稍後再試。"})


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"manage_mode": False})


@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"manage_mode": True})


@app.get("/index.html", include_in_schema=False)
def legacy_home():
    return RedirectResponse(url="/")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return HTMLResponse(status_code=204)
