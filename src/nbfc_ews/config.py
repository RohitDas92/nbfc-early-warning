import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get(
     "EWS_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/ews",
)


AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "")
AZURE_EMBED_DEPLOYMENT = os.environ.get("AZURE_EMBED_DEPLOYMENT", "")
AZURE_DOCINT_ENDPOINT = os.getenv("AZURE_DOCINT_ENDPOINT", "")
AZURE_DOCINT_KEY = os.getenv("AZURE_DOCINT_KEY", "")

AZURE_CHAT_DEPLOYMENT = os.environ.get("AZURE_CHAT_DEPLOYMENT", "")