$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
# Use --wwr only after reviewing source terms and enabling network access.
& .\.venv\Scripts\python.exe -m job_tracker.cli run
exit $LASTEXITCODE
