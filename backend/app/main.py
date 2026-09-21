from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import cashflow, documents

app = FastAPI(
    title="Securitization Document Intelligence & Cash Flow Toolkit",
    description=(
        "Module A: extracts structured fields from real SEC-filed ABS/RMBS "
        "offering documents. Module B: simplified sequential-pay cash flow "
        "waterfall engine with Excel export. See README.md for scope, "
        "assumptions, and data sourcing."
    ),
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(cashflow.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
