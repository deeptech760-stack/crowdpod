# Starts the API (port 8000) in its own window and the UI (port 3000) here. Close both to stop.
Set-Location (Join-Path $PSScriptRoot "..")
Start-Process -FilePath "uv" -ArgumentList "run", "crowdpod", "serve" -WorkingDirectory (Join-Path (Get-Location) "backend")
Write-Host "Open http://localhost:3000/app/"
Push-Location frontend
npm.cmd run dev
Pop-Location
