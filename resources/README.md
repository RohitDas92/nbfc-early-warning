# resources

Generated synthetic book. Not committed — see `docs/16-book-v2-upgrade.md`.

To rebuild:

    python gen/generate.py --out gen/out
    python gen/load.py --dsn "postgresql://postgres:postgres@localhost:5432/ews" --schema --data