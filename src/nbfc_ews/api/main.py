""" The HTTP entry point.

    uvivorn nbfc_ews.api.main:app --reload
    
Interactive docs at http://127.0.0.1:8000/docs
"""

import logging

from fastapi import FastAPI

from nbfc_ews.api.routers import cases

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(messages)s")

app = FastAPI(
    title = "NBFC Early Warning",
    version="0.1.0",
    description="Case queue and agent investigations for an education-loan NBFC."
)
app.include_router(cases.router)

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

