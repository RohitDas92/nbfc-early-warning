"""Find which Azure endpoint and path actually serves our embedding deployment."""

import json
import urllib.error
import urllib.request

from nbfc_ews.config import (
    AZURE_EMBED_DEPLOYMENT as DEP,
)
from nbfc_ews.config import (
    AZURE_OPENAI_API_KEY as KEY,
)
from nbfc_ews.config import (
    AZURE_OPENAI_ENDPOINT as ENDPOINT,
)

resource = ENDPOINT.split("//")[1].split(".")[0]

HOSTS = [
    f"https://{resource}.services.ai.azure.com",
    f"https://{resource}.openai.azure.com",
]

CANDIDATES = [
    ("classic", "/openai/deployments/{d}/embeddings?api-version=2024-02-01",
     {"input": ["hello"]}),
    ("v1", "/openai/v1/embeddings",
     {"model": DEP, "input": ["hello"]}),
    ("foundry", "/models/embeddings?api-version=2024-05-01-preview",
     {"model": DEP, "input": ["hello"]}),
]

print(f"resource={resource!r} deployment={DEP!r}\n")

for host in HOSTS:
    for label, path, body in CANDIDATES:
        url = host + path.replace("{d}", DEP)
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "api-key": KEY},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read())
                dims = len(payload["data"][0]["embedding"])
                print(f"OK    {label:8} {host}  -> {dims} dims")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:120].replace("\n", " ")
            print(f"{exc.code}   {label:8} {host}  {detail}")
        except urllib.error.URLError as exc:
            print(f"DNS   {label:8} {host}  {exc.reason}")