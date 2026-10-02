"""财务报税系统 FastAPI 后端入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import engine, Base, ensure_books
from .seed import ensure_seed
from .routers import accounts, vouchers, books, reports, carryover, settings, data_io, booksets

Base.metadata.create_all(bind=engine)
ensure_seed()
ensure_books()

app = FastAPI(title="财务报税系统", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(accounts.router)
app.include_router(vouchers.router)
app.include_router(books.router)
app.include_router(reports.router)
app.include_router(carryover.router)
app.include_router(settings.router)
app.include_router(data_io.router)
app.include_router(booksets.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
