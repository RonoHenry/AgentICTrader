# Run every AgentICTrader test suite (root + backend) and exit nonzero if any
# test fails. Thin wrapper around scripts/run_all_tests.py; see README "Testing".
#
#   .\run_tests.ps1                    # all suites; live-service tests deselected
#   .\run_tests.ps1 -Live              # + tests marked infrastructure; starts
#                                      #   docker/docker-compose.test.yml first
#   .\run_tests.ps1 -Coverage          # + per-suite coverage report (pytest-cov)
#   .\run_tests.ps1 -Suite backend     # one suite (root, backend); repeat with commas
#   .\run_tests.ps1 -- -x -k risk      # arguments after -- are passed to pytest
#   .\run_tests.ps1 -DryRun            # print the pytest commands, run nothing
#
# -UnitOnly is accepted for compatibility: skipping live-service tests is now
# the default.
param(
    [switch]$Live,
    [switch]$Coverage,
    [switch]$UnitOnly,
    [switch]$DryRun,
    [ValidateSet("root", "backend")]
    [string[]]$Suite,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$repoRoot = $PSScriptRoot
Set-Location $repoRoot

# Interpreter: the active virtualenv, else .\.venv, else python on PATH.
# (VIRTUAL_ENV is checked directly: it can be inherited without its Scripts
# directory being first on PATH.)
if ($env:VIRTUAL_ENV -and (Test-Path "$env:VIRTUAL_ENV\Scripts\python.exe")) {
    $python = "$env:VIRTUAL_ENV\Scripts\python.exe"
} elseif (Test-Path "$repoRoot\.venv\Scripts\python.exe") {
    $python = "$repoRoot\.venv\Scripts\python.exe"
} else {
    $python = "python"
}

if ($UnitOnly -and $Live) {
    Write-Error "-UnitOnly and -Live are mutually exclusive"
    exit 4
}

$runnerArgs = @()
foreach ($s in $Suite) { $runnerArgs += @("--suite", $s) }
if ($DryRun) { $runnerArgs += "--dry-run" }
if ($Live) { $runnerArgs += "--live" }

$extra = @()
if ($Coverage) {
    & $python -c "import pytest_cov" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "-Coverage needs pytest-cov (pip install pytest-cov)"
        exit 4
    }
    $extra += @("--cov", "--cov-report=term-missing")
}
if ($PytestArgs) { $extra += $PytestArgs }

if ($Live -and -not $DryRun) {
    # Live tests need the test services (InfluxDB) from docker-compose.test.yml.
    # Qdrant / MLflow / Kafka-backed tests additionally need those services running.
    $dockerUp = $false
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        docker info *> $null
        $dockerUp = ($LASTEXITCODE -eq 0)
    }
    if ($dockerUp) {
        Write-Host "Starting test services (docker/docker-compose.test.yml)..."
        docker compose -f docker/docker-compose.test.yml up -d --wait
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Test services failed to start; live tests will fail."
        }
    } else {
        Write-Warning "Docker is not available; live tests that need it will fail."
    }
}

& $python scripts/run_all_tests.py @runnerArgs -- @extra
exit $LASTEXITCODE
