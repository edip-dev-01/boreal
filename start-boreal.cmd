@echo off
setlocal DisableDelayedExpansion
title Boreal local demo
set "BOREAL_LAUNCH_ROOT=%~dp0"
rem Inline commands only: no script-policy changes, downloaded code, or elevation.
powershell.exe -NoLogo -NoProfile -Command ^
  "& {" ^
  "function Stop-Boreal([string]$Message) {" ^
  "$problem = New-Object InvalidOperationException($Message); $problem.Data['BorealSafe'] = $true; throw $problem;" ^
  "};" ^
  "function Find-Docker {" ^
  "$command = Get-Command docker.exe -CommandType Application -ErrorAction SilentlyContinue;" ^
  "if (!$command) { Stop-Boreal 'Docker Desktop is missing. Get it at https://www.docker.com/products/docker-desktop/, start it, then try again.' };" ^
  "return $command.Source;" ^
  "};" ^
  "function Invoke-Docker([string[]]$Arguments, [string]$Failure) {" ^
  "$ErrorActionPreference = 'Continue'; $result = & $script:Docker @Arguments 2>$null;" ^
  "if ($LASTEXITCODE -ne 0) { Stop-Boreal $Failure }; return $result;" ^
  "};" ^
  "function Get-BorealHealth([string]$Url) {" ^
  "$request = [Net.WebRequest]::Create($Url + '/api/health');" ^
  "$request.Proxy = $null; $request.AllowAutoRedirect = $false; $request.Timeout = 3000; $request.ReadWriteTimeout = 3000;" ^
  "$response = $request.GetResponse();" ^
  "try { $reader = New-Object IO.StreamReader($response.GetResponseStream()); try { return ($reader.ReadToEnd() | ConvertFrom-Json) } finally { $reader.Dispose() } } finally { $response.Dispose() };" ^
  "};" ^
  "function Open-BorealBrowser([string]$Url) { Start-Process -FilePath $Url };" ^
  "function Start-Boreal([string]$Root, [int]$ReadyTimeoutSeconds = 90) {" ^
  "$ErrorActionPreference = 'Stop';" ^
  "try {" ^
  "if (!(Test-Path -LiteralPath (Join-Path $Root 'compose.yaml') -PathType Leaf)) { Stop-Boreal 'Extract the entire ZIP first. Open start-boreal.cmd in the extracted folder.' };" ^
  "if ($Root.StartsWith('\\')) { Stop-Boreal 'Extract Boreal to a local folder, not a network share.' };" ^
  "$script:Docker = Find-Docker;" ^
  "if ($env:DOCKER_HOST) { Stop-Boreal 'Custom DOCKER_HOST refused. Use local Docker Desktop; consult your administrator.' };" ^
  "Write-Host 'Checking local Docker Desktop...';" ^
  "$context = (Invoke-Docker @('context', 'show') 'Cannot read Docker context. Open Docker Desktop and try again.').Trim();" ^
  "$endpoint = (Invoke-Docker @('context', 'inspect', $context, '--format', '{{.Endpoints.docker.Host}}') 'Cannot inspect the Docker context.').Trim();" ^
  "if ($endpoint -notmatch '^npipe:////\./pipe/[^/]+$') { Stop-Boreal 'Remote Docker context refused. Select your local Docker Desktop context.' };" ^
  "$prefix = @('--context', $context);" ^
  "$os = (Invoke-Docker ($prefix + @('info', '--format', '{{.OSType}}')) 'Docker Desktop is not ready. Open it and wait for the engine, then try again.').Trim();" ^
  "if ($os -ne 'linux') { Stop-Boreal 'Boreal needs Linux containers. Switch Docker Desktop to Linux containers and retry.' };" ^
  "$version = (Invoke-Docker ($prefix + @('compose', 'version', '--short')) 'Docker Compose is missing. Update Docker Desktop.').Trim();" ^
  "if ($version -notmatch '^v?(\d+)\.(\d+)' -or [int]$Matches[1] -lt 2 -or ([int]$Matches[1] -eq 2 -and [int]$Matches[2] -lt 20)) { Stop-Boreal 'Compose 2.20 or newer is required. Update Docker Desktop.' };" ^
  "$env:BUILDX_BUILDER = $context; $env:COMPOSE_BAKE = 'false';" ^
  "$builder = @(Invoke-Docker ($prefix + @('buildx', 'ls', '--format', 'json')) 'Cannot list Docker builders. Update Docker Desktop.' | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object Name -eq $context);" ^
  "if ($builder.Count -ne 1 -or $builder.Driver -ne 'docker' -or @($builder.Nodes).Count -ne 1 -or $builder.Nodes[0].Endpoint -ne $context) { Stop-Boreal 'Unsupported or remote builder. Update Docker Desktop and use its built-in builder.' };" ^
  "$envPath = Join-Path $Root '.env';" ^
  "if (!(Test-Path -LiteralPath $envPath)) {" ^
  "$volume = Invoke-Docker ($prefix + @('volume', 'ls', '--filter', 'name=^boreal_boreal-data$', '--format', '{{.Name}}')) 'Cannot check for existing demo data.';" ^
  "if ($volume) { Stop-Boreal 'Existing Boreal data found without .env. Restore its matching .env. No credentials or data were changed.' };" ^
  "Write-Host 'Creating private local demo credentials...';" ^
  "$rng = [Security.Cryptography.RandomNumberGenerator]::Create();" ^
  "try { $lines = @('# Generated local demo credentials. Do not commit or reuse elsewhere.'); foreach ($name in @('DB_ADMIN_PASSWORD', 'DB_APP_PASSWORD', 'DB_INGEST_PASSWORD')) { $bytes = New-Object byte[] 32; $rng.GetBytes($bytes); $lines += $name + '=' + ([BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()) } } finally { $rng.Dispose() };" ^
  "$lines += @('BOREAL_PORT=8080', 'AS_OF=2026-10-11T12:00:00Z', '');" ^
  "$acl = New-Object Security.AccessControl.FileSecurity; $acl.SetAccessRuleProtection($true, $false);" ^
  "$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User;" ^
  "$acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'Allow')));" ^
  "$temp = $envPath + '.' + [Guid]::NewGuid().ToString('N') + '.tmp';" ^
  "try {" ^
  "$stream = [IO.File]::Create($temp, 4096, [IO.FileOptions]::None, $acl);" ^
  "try { $bytes = [Text.Encoding]::UTF8.GetBytes(($lines -join [char]10)); $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() };" ^
  "try { [IO.File]::Move($temp, $envPath) } catch { if (!(Test-Path -LiteralPath $envPath -PathType Leaf)) { throw } };" ^
  "} finally { if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force } };" ^
  "} else { Write-Host 'Keeping your existing .env unchanged.' };" ^
  "foreach ($name in @('DB_ADMIN_PASSWORD', 'DB_APP_PASSWORD', 'DB_INGEST_PASSWORD', 'BOREAL_PORT', 'AS_OF', 'COMPOSE_PROFILES')) { [Environment]::SetEnvironmentVariable($name, $null, 'Process') };" ^
  "$compose = $prefix + @('compose', '--project-name', 'boreal', '--file', (Join-Path $Root 'compose.yaml'), '--env-file', $envPath);" ^
  "$config = (Invoke-Docker ($compose + @('config', '--format', 'json')) 'Invalid .env or Compose configuration; not replaced. See README.md troubleshooting.') -join [char]10 | ConvertFrom-Json;" ^
  "$ports = @($config.services.web.ports); $port = 0;" ^
  "if ($ports.Count -ne 1 -or $ports[0].host_ip -ne '127.0.0.1' -or $ports[0].target -ne 8080 -or ![int]::TryParse([string]$ports[0].published, [ref]$port) -or $port -lt 1 -or $port -gt 65535) { Stop-Boreal 'Invalid loopback web port. Check BOREAL_PORT in .env and compose.yaml.' };" ^
  "foreach ($service in $config.services.PSObject.Properties) { if ($service.Name -ne 'web' -and $service.Value.ports) { Stop-Boreal 'Only web may publish a port. Restore the original compose.yaml.' } };" ^
  "Write-Host 'Building and starting Boreal. First run may take several minutes to download images.';" ^
  "$null = Invoke-Docker ($compose + @('up', '--build', '-d', '--wait', '--wait-timeout', '180', 'web')) 'Startup failed. Check Docker Desktop, disk space, and BOREAL_PORT conflicts. Your .env and data were kept.';" ^
  "$url = 'http://127.0.0.1:' + $port; $deadline = [DateTime]::UtcNow.AddSeconds($ReadyTimeoutSeconds);" ^
  "Write-Host 'Waiting for the Boreal web page and database...';" ^
  "do {" ^
  "try { $health = Get-BorealHealth $url } catch { $health = $null };" ^
  "if ($health -and $health.status -eq 'ok' -and $health.product -eq 'Boreal' -and ($health.synthetic -is [bool]) -and $health.synthetic -and $health.runtime -eq 'postgres') {" ^
  "Write-Host ('Boreal is ready at ' + $url);" ^
  "try { Open-BorealBrowser $url } catch { Write-Host ('Open this address in your browser: ' + $url) };" ^
  "Write-Host 'Choose Demo reader or Demo analyst. Closing this window leaves Boreal running.'; return 0;" ^
  "};" ^
  "if ([DateTime]::UtcNow -lt $deadline) { Start-Sleep -Seconds 2 };" ^
  "} while ([DateTime]::UtcNow -lt $deadline);" ^
  "Stop-Boreal 'Boreal health check timed out. See Docker Desktop and README.md. No browser opened; .env and data were kept.';" ^
  "} catch { $message = 'Unexpected startup error. Check folder permissions and README.md troubleshooting.'; if ($_.Exception.Data['BorealSafe']) { $message = $_.Exception.Message }; Write-Host ('Boreal could not start: ' + $message); return 1 };" ^
  "};" ^
  "exit (Start-Boreal -Root $env:BOREAL_LAUNCH_ROOT);" ^
  "}"
set "BOREAL_EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%BOREAL_EXIT_CODE%"=="0" echo See README.md for help. No security settings were changed.
echo Press any key to close this window.
pause >nul
exit /b %BOREAL_EXIT_CODE%
