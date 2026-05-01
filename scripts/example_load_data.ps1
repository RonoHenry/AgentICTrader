# Example PowerShell script to load historical data from OANDA
# This demonstrates various usage patterns

# Ensure environment variables are set
if (-not $env:OANDA_API_KEY) {
    Write-Host "Error: OANDA_API_KEY not set" -ForegroundColor Red
    Write-Host "Please set: `$env:OANDA_API_KEY='your_key_here'"
    exit 1
}

if (-not $env:TIMESCALE_URL) {
    Write-Host "Error: TIMESCALE_URL not set" -ForegroundColor Red
    Write-Host "Please set: `$env:TIMESCALE_URL='postgresql+asyncpg://user:pass@host:port/db'"
    exit 1
}

Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host "AgentICTrader Historical Data Loading Examples" -ForegroundColor Cyan
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host ""

# Example 1: Load a single instrument-timeframe for testing
Write-Host "Example 1: Load EURUSD H1 data (quick test)" -ForegroundColor Yellow
Write-Host "-------------------------------------------------------------------"
python scripts/load_historical_data.py --instrument EURUSD --timeframe H1
Write-Host ""

# Example 2: Load all timeframes for a single instrument
Write-Host "Example 2: Load all EURUSD timeframes" -ForegroundColor Yellow
Write-Host "-------------------------------------------------------------------"
python scripts/load_historical_data.py --instrument EURUSD
Write-Host ""

# Example 3: Load a specific timeframe for all instruments
Write-Host "Example 3: Load D1 data for all instruments" -ForegroundColor Yellow
Write-Host "-------------------------------------------------------------------"
python scripts/load_historical_data.py --timeframe D1
Write-Host ""

# Example 4: Load everything (this will take 2-4 hours)
Write-Host "Example 4: Load all instruments and timeframes (FULL LOAD)" -ForegroundColor Yellow
Write-Host "-------------------------------------------------------------------"
Write-Host "WARNING: This will take 2-4 hours to complete!" -ForegroundColor Red
$response = Read-Host "Continue? (y/n)"
if ($response -eq 'y' -or $response -eq 'Y') {
    python scripts/load_historical_data.py
}
Write-Host ""

# Example 5: Resume interrupted load
Write-Host "Example 5: Resume interrupted load" -ForegroundColor Yellow
Write-Host "-------------------------------------------------------------------"
python scripts/load_historical_data.py --resume
Write-Host ""

Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host "Examples completed!" -ForegroundColor Cyan
Write-Host "===================================================================" -ForegroundColor Cyan
