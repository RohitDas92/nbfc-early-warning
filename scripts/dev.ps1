# Local development shortcuts.  Not committed - see .gitignore
#
#   . .\scripts\dev.ps1        load into this terminal (note the leading dot)
#
#   act        activate the virtualenv
#   t / tq     pytest / pytest -q
#   repl       python REPL with conn and the pipeline already imported
#   det        run detection, e.g.  det 2026-04-01 2026-05-01 2026-06-01
#   db         psql into the Postgres container
#   reinst     pip install -e .   (after changing pyproject.toml)

$Root = Split-Path -Parent $PSScriptRoot
$PgContainer = "ews-postgres"          

function act    { & "$Root\.venv\Scripts\Activate.ps1"; Write-Host "venv active" -ForegroundColor Green }
function t      { pytest @args }
function tq     { pytest -q @args }
function repl   { python -i "$Root\scripts\shell.py" }
function det    { python "$Root\scripts\detect_run.py" @args }
function db     { docker exec -it $PgContainer psql -U postgres -d ews }
function reinst { pip install -e "$Root" }
function nightly { python "$Root\scripts\nightly.py" @args }

Write-Host "commands:  act  t  tq  repl  det  db  reinst" -ForegroundColor Cyan
