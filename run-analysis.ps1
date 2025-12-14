# ADE EPC Analysis - Run National Pipeline
# Lightweight wrapper to run the current national analyzers

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "ADE EPC Analysis" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Activate virtual environment if available
if (-not $env:VIRTUAL_ENV -and (Test-Path "venv\Scripts\Activate.ps1")) {
    Write-Host "Activating virtual environment..." -ForegroundColor Yellow
    & .\venv\Scripts\Activate.ps1
}

# Run the pipeline
$command = "python run_ade_analysis.py"
Write-Host "Running: $command" -ForegroundColor Cyan
Invoke-Expression $command

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "✓ Analysis Complete!" -ForegroundColor Green
    Write-Host "Outputs: data\\outputs\\" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "✗ Analysis failed" -ForegroundColor Red
    exit 1
}
