# Install Visual Studio Build Tools via PowerShell
# No GUI, automated installation
#
# This installs ONLY the C++ compiler and Windows SDK needed for webrtcvad
# (~2-3 GB vs 6-8 GB with GUI installer)

Write-Host "Installing Visual Studio Build Tools for C++ compilation..." -ForegroundColor Green

# Download installer
$installerUrl = "https://aka.ms/vs/17/release/vs_buildtools.exe"
$installerPath = "$env:TEMP\vs_buildtools.exe"

Write-Host "Downloading Build Tools installer..." -ForegroundColor Yellow
Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath

# Install with minimal components (C++ only)
# --quiet: No GUI
# --wait: Wait for installation to complete
# --norestart: Don't restart automatically
# --nocache: Don't keep installer cache (saves space)
Write-Host "Installing C++ Build Tools (this takes 10-15 minutes)..." -ForegroundColor Yellow
Write-Host "Installation is running in background. Please wait..." -ForegroundColor Cyan

$arguments = @(
    "--quiet",
    "--wait",
    "--norestart",
    "--nocache",
    "--add", "Microsoft.VisualStudio.Workload.VCTools",
    "--add", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
    "--add", "Microsoft.VisualStudio.Component.Windows11SDK.22000"
)

$process = Start-Process -FilePath $installerPath -ArgumentList $arguments -Wait -PassThru

if ($process.ExitCode -eq 0 -or $process.ExitCode -eq 3010) {
    Write-Host "✓ Build Tools installed successfully!" -ForegroundColor Green

    if ($process.ExitCode -eq 3010) {
        Write-Host "⚠ Restart required for changes to take effect" -ForegroundColor Yellow
    }

    # Clean up installer
    Remove-Item $installerPath -Force

    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "1. Restart your computer (if required)"
    Write-Host "2. Run: conda activate cqsentinel"
    Write-Host "3. Run: pip install resemblyzer"
    Write-Host "4. Test: python -c `"from resemblyzer import VoiceEncoder; print('✓ Works!')`""

} else {
    Write-Host "✗ Installation failed with exit code: $($process.ExitCode)" -ForegroundColor Red
    Write-Host "Check logs at: $env:TEMP\dd_bootstrapper*.log" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Installation complete!" -ForegroundColor Green
