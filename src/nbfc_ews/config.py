import os

DATABASE_URL = os.environ.get(
     "EWS_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/ews",
)
