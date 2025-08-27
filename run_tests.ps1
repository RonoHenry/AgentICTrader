# Parse command line arguments
param(
    [switch]$UnitOnly,
    [Parameter(ValueFromRemainingArguments=$true)]
    $RemainingArgs
)

# Function to check if a command exists
function Test-Command($command) {
    try {
        $null = Get-Command $command -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

# Function to check if Docker container is running
function Test-DockerContainer($containerName) {
    try {
        $running = docker ps --filter "name=$containerName" --format '{{.Names}}'
        return $running -eq $containerName
    } catch {
        return $false
    }
}

# Check Docker requirement
$dockerAvailable = $false
if (-not $UnitOnly) {
    Write-Host "Checking Docker availability..."
    # Check if Docker is installed
    if (-not (Test-Command docker)) {
        Write-Warning "Docker is not installed. Running unit tests only. For full test suite, please install Docker Desktop."
        $UnitOnly = $true
    } else {
        # Check if Docker is running
        try {
            $null = docker info 2>&1
            $dockerAvailable = $true
        } catch {
            Write-Warning "Docker is not running. Running unit tests only. For full test suite, please start Docker Desktop."
            $UnitOnly = $true
        }
    }
}

if (-not $UnitOnly) {
    # Ensure test services are running
    Write-Host "Ensuring test services are running..."
    docker compose -f docker/docker-compose.test.yml up -d

    # Wait for services to be ready
    $maxWait = 30
    $waited = 0
    while ($waited -lt $maxWait) {
        $influxHealth = $(docker ps --filter "name=agentictrader_influxdb" --format "{{.Status}}")
        if ($influxHealth -match "Up") {
            break
        }
        Write-Host "Waiting for services to be ready..."
        Start-Sleep -Seconds 1
        $waited++
    }

    if ($waited -eq $maxWait) {
        Write-Error "Timeout waiting for services to be ready"
        exit 1
    }
}

# Set environment variables
$backendPath = "$(Get-Location)\backend"
if (-not $env:PYTHONPATH) {
    $env:PYTHONPATH = $backendPath
} else {
    $paths = $env:PYTHONPATH -split ";"
    if ($paths -notcontains $backendPath) {
        $env:PYTHONPATH = "$backendPath;$env:PYTHONPATH"
    }
}
$env:DJANGO_SETTINGS_MODULE = "agentictrader.settings_test"

Write-Host "Activating virtual environment..."
try {
    & "$(Get-Location)\agentic.venv\Scripts\Activate.ps1"
} catch {
    Write-Error "Failed to activate virtual environment. Please ensure it exists and is properly set up."
    exit 1
}

# Run tests with coverage
Write-Host "Running tests..."
try {
    # Check if pytest-cov is installed
    if (-not (python -c "import pytest_cov" 2>$null)) {
        Write-Host "Installing pytest-cov for coverage reporting..."
        pip install pytest-cov
    }
    
    # Build test command
    $testCmd = "pytest --cov=backend --cov-report=term-missing"
    if ($UnitOnly) {
        Write-Host "Running unit tests only (no Docker required)..."
        $testCmd += ' -k "not (client or bucket or connection or retention or influxdb)"'
    }
    if ($RemainingArgs) {
        $testCmd += " $RemainingArgs"
    }
    
    # Run tests
    Invoke-Expression $testCmd
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Tests failed with exit code $LASTEXITCODE"
        exit $LASTEXITCODE
    }
} catch {
    Write-Error "Error running tests: $_"
    exit 1
}

Write-Host "Tests completed successfully!" -ForegroundColor Green
