# Dependency-free Windows PowerShell 5.1 regression tests. Docker is never needed.
# Parse the readable inline payload before loading only its function definitions.
# External boundaries are mocked below; a separate cmd.exe smoke checks the real
# batch-to-PowerShell boundary. No execution-policy setting is changed by tests.
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$LauncherPath = Join-Path $RepoRoot 'start-boreal.cmd'
$script:Passed = 0
$script:Failed = 0
$script:TempRoot = Join-Path ([IO.Path]::GetTempPath()) ('Boreal launcher tests ' + [guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($script:TempRoot)

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}
function Assert-Equal {
    param($Actual, $Expected, [string]$Message)
    if ($Actual -cne $Expected) { throw "$Message (expected '$Expected'; got '$Actual')" }
}
function Test-Case {
    param([string]$Name, [scriptblock]$Body)
    try {
        & $Body
        $script:Passed++
        Write-Host "PASS: $Name"
    } catch {
        $script:Failed++
        Write-Host "FAIL: $Name -- $($_.Exception.Message)"
    }
}
function Get-InlinePayload {
    param([string]$Path)
    $lines = [IO.File]::ReadAllLines($Path)
    $prefix = 'powershell.exe -NoLogo -NoProfile -Command '
    $start = -1
    for ($i = 0; $i -lt $lines.Length; $i++) {
        if ($lines[$i] -ceq ($prefix + '^')) { $start = $i; break }
    }
    Assert-True ($start -ge 0) 'Missing readable inline PowerShell command.'
    $logicalParts = New-Object 'System.Collections.Generic.List[string]'
    $payloadParts = New-Object 'System.Collections.Generic.List[string]'
    $logicalParts.Add($prefix)
    $ended = $false
    for ($i = $start + 1; $i -lt $lines.Length; $i++) {
        $rawLine = $lines[$i]
        $continued = $rawLine.EndsWith(' ^')
        if ($continued) { $logicalParts.Add($rawLine.Substring(0, $rawLine.Length - 1)) }
        else { $logicalParts.Add($rawLine) }
        $line = $rawLine.TrimStart()
        if ($continued) { $line = $line.Substring(0, $line.Length - 2) }
        Assert-True ($line -match '^"[^"\r\n]*"$') 'Each inline argument must have balanced outer quotes, with its continuation caret outside them.'
        $payloadParts.Add($line.Substring(1, $line.Length - 2))
        if (-not $continued) { $ended = $true; break }
    }
    Assert-True $ended 'Inline PowerShell command is missing its final line.'
    $logical = $logicalParts -join ''
    Assert-True ($logical.Length -lt 8191) 'Inline logical command exceeds the cmd.exe 8191-character limit.'
    Assert-True ($logical -notmatch '%') 'Environment expansion must not grow the inline command beyond the cmd.exe limit.'
    return ($payloadParts -join ' ')
}
function Get-HexHash {
    param([byte[]]$Bytes)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}
function Stop-NativeTestProcess {
    param([Diagnostics.Process]$Process)
    if (-not $Process.HasExited) {
        # Killing cmd.exe alone leaves its PowerShell child holding the test folder.
        $ErrorActionPreference = 'Continue'
        & (Join-Path $env:SystemRoot 'System32\taskkill.exe') /PID $Process.Id /T /F *> $null
        if (-not $Process.WaitForExit(10000)) {
            $Process.Kill()
            [void]$Process.WaitForExit(5000)
        }
    }
}

try {
    Test-Case 'launcher is readable, parseable Windows PowerShell with no policy bypass' {
        $source = [IO.File]::ReadAllText($LauncherPath)
        Assert-True ($source -notmatch '(?i)ExecutionPolicy|EncodedCommand|Invoke-Expression|\biex\b|FromBase64String|\.ps1\b') 'Launcher must not load script files, decode/evaluate payloads, or change execution policy.'
        $script:Payload = Get-InlinePayload $LauncherPath
        $tokens = $null
        $errors = $null
        $script:PayloadAst = [Management.Automation.Language.Parser]::ParseInput($script:Payload, [ref]$tokens, [ref]$errors)
        Assert-Equal @($errors).Count 0 ('Inline PowerShell syntax errors: ' + ($errors | Out-String))
        $script:FunctionAsts = @($script:PayloadAst.FindAll({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] }, $true))
        foreach ($name in @('Stop-Boreal', 'Find-Docker', 'Invoke-Docker', 'Get-BorealHealth', 'Open-BorealBrowser', 'Start-Boreal')) {
            Assert-True ($script:FunctionAsts.Name -contains $name) "Missing launcher function $name."
        }
    }
    if ($script:Failed) { throw 'Cannot safely load invalid launcher source.' }

    # Only definitions are evaluated, never the launcher exit/pause trailer.
    . ([scriptblock]::Create(($script:FunctionAsts | ForEach-Object { $_.Extent.Text }) -join "`n"))

    Test-Case 'immutable synthetic fixtures survive Windows checkout byte-for-byte' {
        foreach ($line in [IO.File]::ReadAllLines((Join-Path $RepoRoot 'docs/fixture-checksums.sha256'))) {
            if (-not $line.Trim()) { continue }
            Assert-True ($line -match '^([0-9a-f]{64})  (.+)$') 'Invalid fixture manifest record.'
            $expected = $Matches[1]
            $relativePath = $Matches[2]
            $path = Join-Path $RepoRoot ($relativePath.Replace('/', [IO.Path]::DirectorySeparatorChar))
            Assert-Equal (Get-HexHash ([IO.File]::ReadAllBytes($path))) $expected "Fixture changed: $relativePath"
        }
    }

    $originalInvokeDocker = (Get-Command Invoke-Docker).ScriptBlock

    Test-Case 'controlled errors preserve their safe message marker' {
        $caught = $null
        try { Stop-Boreal 'Safe troubleshooting message.' } catch { $caught = $_ }
        Assert-True ($null -ne $caught) 'Stop-Boreal must stop execution.'
        Assert-Equal $caught.Exception.Message 'Safe troubleshooting message.' 'Safe error text was lost.'
        Assert-Equal $caught.Exception.Data['BorealSafe'] $true 'Safe error marker was lost.'
    }

    # Save the inherited process settings because the launcher deliberately clears
    # Compose interpolation overrides. Tests must not affect the caller's shell.
    $savedEnvironment = @{}
    foreach ($name in @('DOCKER_HOST', 'DOCKER_CONTEXT', 'BUILDX_BUILDER', 'COMPOSE_BAKE', 'DB_ADMIN_PASSWORD', 'DB_APP_PASSWORD', 'DB_INGEST_PASSWORD', 'BOREAL_PORT', 'AS_OF', 'COMPOSE_PROFILES')) {
        $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    }

    function New-Scenario {
        $root = Join-Path $script:TempRoot ([guid]::NewGuid().ToString('N') + ' demo & (local)')
        [void][IO.Directory]::CreateDirectory($root)
        Copy-Item -LiteralPath (Join-Path $RepoRoot 'compose.yaml') -Destination $root
        Copy-Item -LiteralPath (Join-Path $RepoRoot '.env.example') -Destination $root
        $config = [ordered]@{
            services = [ordered]@{
                web = @{ ports = @(@{ host_ip = '127.0.0.1'; target = 8080; published = '8080' }) }
                db = @{}
                api = @{}
                ingest = @{}
            }
        }
        $script:Scenario = @{
            Root = $root
            DockerPresent = $true
            DockerRunning = $true
            Context = 'desktop-linux'
            Endpoint = 'npipe:////./pipe/dockerDesktopLinuxEngine'
            Engine = 'linux'
            ComposeVersion = '2.40.0'
            Builder = @{ Name = 'desktop-linux'; Driver = 'docker'; Nodes = @(@{ Endpoint = 'desktop-linux' }) }
            BuilderJson = $null
            ExistingVolume = ''
            FailOn = ''
            Config = $config
            ConfigJson = $null
            Health = [pscustomobject]@{ status = 'ok'; product = 'Boreal'; synthetic = $true; runtime = 'postgres' }
            HealthThrows = $false
            HealthCalls = 0
            HealthUrls = New-Object 'System.Collections.Generic.List[string]'
            BrowserThrows = $false
            BrowserUrls = New-Object 'System.Collections.Generic.List[string]'
            Calls = New-Object 'System.Collections.Generic.List[object]'
        }
        [Environment]::SetEnvironmentVariable('DOCKER_HOST', $null, 'Process')
        [Environment]::SetEnvironmentVariable('DOCKER_CONTEXT', $null, 'Process')
        [Environment]::SetEnvironmentVariable('BUILDX_BUILDER', $null, 'Process')
        [Environment]::SetEnvironmentVariable('COMPOSE_BAKE', $null, 'Process')
    }
    function Set-ExistingEnv {
        param([byte[]]$Bytes = [Text.Encoding]::UTF8.GetBytes("# User-edited .env`r`nDB_ADMIN_PASSWORD=local-fixture-admin`r`nDB_APP_PASSWORD=local-fixture-app`r`nDB_INGEST_PASSWORD=local-fixture-ingest`r`nBOREAL_PORT=8080`r`n"))
        [IO.File]::WriteAllBytes((Join-Path $script:Scenario.Root '.env'), $Bytes)
    }
    function Find-Docker {
        if (-not $script:Scenario.DockerPresent) { Stop-Boreal 'Docker Desktop was not found. Install Docker Desktop and try again.' }
        return 'mock-docker.exe'
    }
    function Invoke-Docker {
        param([string[]]$Arguments, [string]$Failure)
        $s = $script:Scenario
        [void]$s.Calls.Add([pscustomobject]@{ Arguments = @($Arguments); Builder = $env:BUILDX_BUILDER; Bake = $env:COMPOSE_BAKE })
        $words = $Arguments -join ' '
        if ($s.FailOn -and $words -match $s.FailOn) { Stop-Boreal $Failure }
        if ($words -eq 'context show') { return $s.Context }
        if ($Arguments[0] -eq 'context' -and $Arguments[1] -eq 'inspect') { return $s.Endpoint }
        if ($Arguments -contains 'info') {
            if (-not $s.DockerRunning) { Stop-Boreal $Failure }
            return $s.Engine
        }
        if ($Arguments -contains 'compose' -and $Arguments -contains 'version') { return $s.ComposeVersion }
        if ($Arguments -contains 'buildx' -and $Arguments -contains 'inspect') {
            throw 'Launcher must use the supported buildx ls JSON interface.'
        }
        if ($Arguments -contains 'buildx' -and $Arguments -contains 'ls') {
            if ($Arguments[-2] -ne '--format' -or $Arguments[-1] -ne 'json') { throw 'buildx ls needs --format json for this contract.' }
            if ($null -ne $s.BuilderJson) { return $s.BuilderJson }
            return ($s.Builder | ConvertTo-Json -Depth 8 -Compress)
        }
        if ($Arguments -contains 'volume' -and $Arguments -contains 'ls') { return $s.ExistingVolume }
        if ($Arguments -contains 'config') {
            if ($null -ne $s.ConfigJson) { return $s.ConfigJson }
            return ($s.Config | ConvertTo-Json -Depth 12 -Compress)
        }
        if ($Arguments -contains 'up') { return 'Compose completed successfully.' }
        throw "Unexpected mocked Docker invocation: $words"
    }
    function Get-BorealHealth {
        param([string]$Url)
        $script:Scenario.HealthCalls++
        [void]$script:Scenario.HealthUrls.Add($Url)
        if ($script:Scenario.HealthThrows) { throw 'Simulated connection timeout.' }
        return $script:Scenario.Health
    }
    function Open-BorealBrowser {
        param([string]$Url)
        [void]$script:Scenario.BrowserUrls.Add($Url)
        if ($script:Scenario.BrowserThrows) { throw 'No default browser is configured.' }
    }
    function Invoke-Scenario {
        $script:Result = $null
        $script:Captured = (@(& { $script:Result = Start-Boreal -Root $script:Scenario.Root -ReadyTimeoutSeconds 0 } *>&1) | Out-String)
        Assert-Equal @($script:Result).Count 1 'Launcher must return one exit status, without leaking Docker output.'
    }
    function Assert-Failure {
        Assert-Equal $script:Result 1 'Expected actionable nonzero launcher result.'
        Assert-Equal $script:Scenario.BrowserUrls.Count 0 'A failed launch must not open a browser.'
        Assert-True ($script:Captured -match 'Boreal could not start:') 'Failure should be explained clearly.'
    }
    function Assert-NoStart {
        Assert-Equal @($script:Scenario.Calls | Where-Object { $_.Arguments -contains 'up' }).Count 0 'Preflight failure must not start containers.'
    }
    function Assert-NoEnv {
        Assert-True (-not (Test-Path -LiteralPath (Join-Path $script:Scenario.Root '.env'))) 'Preflight failure must not create .env.'
    }

    Test-Case 'incomplete extraction fails before Docker or credential changes' {
        New-Scenario
        Remove-Item -LiteralPath (Join-Path $script:Scenario.Root 'compose.yaml')
        Invoke-Scenario
        Assert-Failure
        Assert-NoStart
        Assert-NoEnv
        Assert-Equal $script:Scenario.Calls.Count 0 'Incomplete extraction must not invoke Docker.'
        Assert-True ($script:Captured -match 'Extract the entire ZIP') 'Extraction guidance was lost.'
    }
    Test-Case 'missing Docker fails before creating credentials or starting containers' {
        New-Scenario
        $script:Scenario.DockerPresent = $false
        Invoke-Scenario
        Assert-Failure
        Assert-NoStart
        Assert-NoEnv
        Assert-True ($script:Captured -match 'Docker Desktop') 'Missing Docker guidance was lost.'
    }
    Test-Case 'stopped Docker engine fails without creating credentials' {
        New-Scenario
        $script:Scenario.DockerRunning = $false
        Invoke-Scenario
        Assert-Failure
        Assert-NoStart
        Assert-NoEnv
        Assert-True ($script:Captured -match 'not ready') 'Stopped engine guidance was lost.'
    }
    Test-Case 'Windows-container engine is rejected' {
        New-Scenario
        $script:Scenario.Engine = 'windows'
        Invoke-Scenario
        Assert-Failure
        Assert-NoStart
        Assert-NoEnv
        Assert-True ($script:Captured -match 'Linux containers') 'Linux-container guidance was lost.'
    }
    Test-Case 'remote TCP, SSH and Unix Docker contexts are rejected' {
        foreach ($endpoint in @('tcp://203.0.113.10:2376', 'ssh://example.invalid', 'unix:///var/run/docker.sock')) {
            New-Scenario
            $script:Scenario.Endpoint = $endpoint
            Invoke-Scenario
            Assert-Failure
            Assert-NoStart
            Assert-NoEnv
            Assert-True ($script:Captured -match 'local Docker Desktop') 'Remote-context guidance was lost.'
        }
    }
    Test-Case 'DOCKER_HOST override is rejected even with an otherwise local context' {
        New-Scenario
        $env:DOCKER_HOST = 'tcp://203.0.113.10:2376'
        Invoke-Scenario
        Assert-Failure
        Assert-NoStart
        Assert-NoEnv
        Assert-True ($script:Captured -match 'DOCKER_HOST') 'Docker override guidance was lost.'
    }
    Test-Case 'missing or too-old Compose is rejected before credential creation' {
        foreach ($mode in @('missing', 'v1.29.2', '2.19.1', 'unrecognized')) {
            New-Scenario
            if ($mode -eq 'missing') { $script:Scenario.FailOn = 'compose version' }
            else { $script:Scenario.ComposeVersion = $mode }
            Invoke-Scenario
            Assert-Failure
            Assert-NoStart
            Assert-NoEnv
            Assert-True ($script:Captured -match 'Compose') 'Compose upgrade guidance was lost.'
        }
    }
    Test-Case 'missing, remote or ambiguous Buildx builders fail before creating credentials' {
        foreach ($mode in @('missing', 'docker-container', 'remote', 'kubernetes', 'no-nodes', 'multiple-nodes', 'wrong-endpoint', 'malformed', 'missing-selected', 'duplicate-selected')) {
            New-Scenario
            switch ($mode) {
                'missing' { $script:Scenario.FailOn = 'buildx ls' }
                'docker-container' { $script:Scenario.Builder.Driver = 'docker-container' }
                'remote' { $script:Scenario.Builder.Driver = 'remote' }
                'kubernetes' { $script:Scenario.Builder.Driver = 'kubernetes' }
                'no-nodes' { $script:Scenario.Builder.Nodes = @() }
                'multiple-nodes' { $script:Scenario.Builder.Nodes += @{ Endpoint = 'desktop-linux' } }
                'wrong-endpoint' { $script:Scenario.Builder.Nodes[0].Endpoint = 'tcp://203.0.113.10:2376' }
                'malformed' { $script:Scenario.BuilderJson = '{invalid-json}' }
                'missing-selected' { $script:Scenario.Builder.Name = 'other-builder' }
                'duplicate-selected' {
                    $json = $script:Scenario.Builder | ConvertTo-Json -Depth 8 -Compress
                    $script:Scenario.BuilderJson = @($json, $json)
                }
            }
            Invoke-Scenario
            Assert-Failure
            Assert-NoStart
            Assert-NoEnv
        }
    }
    Test-Case 'Buildx JSON lines select only the verified local context builder' {
        New-Scenario
        Set-ExistingEnv
        $selected = $script:Scenario.Builder | ConvertTo-Json -Depth 8 -Compress
        $other = @{ Name = 'unrelated-remote'; Driver = 'remote'; Nodes = @(@{ Endpoint = 'tcp://203.0.113.10:2376' }) } | ConvertTo-Json -Depth 8 -Compress
        $script:Scenario.BuilderJson = @($other, $selected)
        Invoke-Scenario
        Assert-Equal $script:Result 0 'Unrelated builders must not prevent the verified local builder from starting.'
        Assert-Equal $script:Scenario.BrowserUrls.Count 1 'Valid local builder should permit one browser launch.'
    }
    Test-Case 'missing .env with existing Boreal volume is never reset' {
        New-Scenario
        $script:Scenario.ExistingVolume = 'boreal_boreal-data'
        Invoke-Scenario
        Assert-Failure
        Assert-NoStart
        Assert-NoEnv
        Assert-True ($script:Captured -match 'Restore.*matching .env') 'Existing-data recovery guidance was lost.'
        Assert-Equal @($script:Scenario.Calls | Where-Object { $_.Arguments -contains 'rm' -or $_.Arguments -contains 'down' -or $_.Arguments -contains 'prune' }).Count 0 'Launcher must not destroy existing data.'
    }
    Test-Case 'failed existing-volume check fails closed without generating credentials' {
        New-Scenario
        $script:Scenario.FailOn = 'volume ls'
        Invoke-Scenario
        Assert-Failure
        Assert-NoStart
        Assert-NoEnv
    }
    Test-Case 'new .env has unique cryptographic-size credentials, restrictive ACLs and no console disclosure' {
        New-Scenario
        Invoke-Scenario
        Assert-Equal $script:Result 0 'Fresh launch should succeed.'
        $path = Join-Path $script:Scenario.Root '.env'
        $text = [IO.File]::ReadAllText($path)
        $matches = [regex]::Matches($text, '(?m)^DB_(?:ADMIN|APP|INGEST)_PASSWORD=([0-9a-f]{64})\r?$')
        Assert-Equal $matches.Count 3 'Exactly three 64-hex credentials are required.'
        $secrets = @($matches | ForEach-Object { $_.Groups[1].Value })
        Assert-Equal @($secrets | Select-Object -Unique).Count 3 'Credentials must be distinct.'
        foreach ($secret in $secrets) { Assert-True (-not $script:Captured.Contains($secret)) 'Generated password appeared in console output.' }
        Assert-True ($text -match '(?m)^BOREAL_PORT=8080\r?$') 'Default web port missing.'
        Assert-True ($text -match '(?m)^AS_OF=2026-10-11T12:00:00Z\r?$') 'Deterministic fixture date missing.'
        $acl = Get-Acl -LiteralPath $path
        Assert-True $acl.AreAccessRulesProtected 'Credential ACL must not inherit broad directory permissions.'
        $currentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        $rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
        Assert-True ($rules.Count -gt 0) 'Credentials need an explicit owner access rule.'
        foreach ($rule in $rules) {
            Assert-Equal $rule.IdentityReference.Value $currentSid 'Only the current user may receive .env access.'
            Assert-Equal $rule.AccessControlType ([Security.AccessControl.AccessControlType]::Allow) 'Owner must have usable credential access.'
            Assert-True (-not $rule.IsInherited) 'Credential access rule should be explicit.'
        }
        Assert-Equal @(Get-ChildItem -LiteralPath $script:Scenario.Root -Filter '.env.*.tmp' -Force).Count 0 'Credential temp files must be removed.'
        $first = [IO.File]::ReadAllBytes($path)
        $firstSddl = $acl.Sddl
        Invoke-Scenario
        Assert-Equal $script:Result 0 'Second launch should succeed.'
        Assert-Equal (Get-HexHash ([IO.File]::ReadAllBytes($path))) (Get-HexHash $first) 'Second launch replaced credentials.'
        Assert-Equal (Get-Acl -LiteralPath $path).Sddl $firstSddl 'Second launch changed credential permissions.'
        New-Scenario
        Invoke-Scenario
        $second = [IO.File]::ReadAllText((Join-Path $script:Scenario.Root '.env'))
        foreach ($secret in $secrets) { Assert-True (-not $second.Contains($secret)) 'Different installs reused a generated password.' }
    }
    Test-Case 'existing edited .env is preserved byte-for-byte and never executed' {
        New-Scenario
        $marker = Join-Path $script:Scenario.Root 'executed.txt'
        $bytes = [Text.Encoding]::UTF8.GetBytes("# Preserve CRLF and Unicode: $([char]0x00e9)`r`nBOREAL_PORT=9099`r`nSHELL_PAYLOAD=`$(Set-Content -LiteralPath '$marker' -Value bad)`r`n")
        Set-ExistingEnv $bytes
        Invoke-Scenario
        Assert-Equal $script:Result 0 'A user-managed env should be delegated to Compose.'
        Assert-Equal (Get-HexHash ([IO.File]::ReadAllBytes((Join-Path $script:Scenario.Root '.env')))) (Get-HexHash $bytes) 'Existing env bytes changed.'
        Assert-True (-not (Test-Path -LiteralPath $marker)) 'Launcher evaluated .env as executable code.'
        Assert-Equal @($script:Scenario.Calls | Where-Object { $_.Arguments -contains 'volume' }).Count 0 'Existing credentials must not trigger data-reset checks.'
    }
    Test-Case 'invalid existing .env is preserved and Compose validation failure never opens a browser' {
        New-Scenario
        $bytes = [byte[]]@(0xef, 0xbb, 0xbf) + [Text.Encoding]::UTF8.GetBytes("DB_ADMIN_PASSWORD=`r`ninvalid line = `( `r`n")
        Set-ExistingEnv $bytes
        $script:Scenario.FailOn = 'config --format json'
        Invoke-Scenario
        Assert-Failure
        Assert-NoStart
        Assert-Equal (Get-HexHash ([IO.File]::ReadAllBytes((Join-Path $script:Scenario.Root '.env')))) (Get-HexHash $bytes) 'Invalid .env must not be repaired or overwritten.'
        Assert-True ($script:Captured -match 'Invalid .env or Compose configuration') 'Invalid-env guidance was lost.'
    }
    Test-Case 'malformed Compose JSON is rejected without disclosing interpolated credentials' {
        New-Scenario
        Set-ExistingEnv
        $secret = 'private-config-value-do-not-print'
        $script:Scenario.ConfigJson = '{"DB_ADMIN_PASSWORD":"' + $secret + '", broken}'
        Invoke-Scenario
        Assert-Failure
        Assert-NoStart
        Assert-True (-not $script:Captured.Contains($secret)) 'JSON parse error disclosed a credential.'
    }
    Test-Case 'custom web port comes from resolved Compose JSON and context is pinned' {
        New-Scenario
        Set-ExistingEnv ([Text.Encoding]::UTF8.GetBytes("BOREAL_PORT=9123`r`n"))
        $env:BOREAL_PORT = '4567'
        $env:COMPOSE_PROFILES = 'unwanted-profile'
        $env:BUILDX_BUILDER = 'remote-builder'
        $env:COMPOSE_BAKE = 'true'
        $script:Scenario.Config.services.web.ports[0].published = '9123'
        Invoke-Scenario
        Assert-Equal $script:Result 0 'Custom-port launch should succeed.'
        Assert-Equal $script:Scenario.BrowserUrls.Count 1 'Successful launch should open exactly one browser.'
        Assert-Equal $script:Scenario.BrowserUrls[0] 'http://127.0.0.1:9123' 'Browser must use resolved web port.'
        Assert-Equal $script:Scenario.HealthUrls[0] 'http://127.0.0.1:9123' 'Readiness must probe the resolved web port.'
        $configCalls = @($script:Scenario.Calls | Where-Object { $_.Arguments -contains 'config' })
        Assert-Equal $configCalls.Count 1 'Compose configuration must be resolved exactly once.'
        $upCalls = @($script:Scenario.Calls | Where-Object { $_.Arguments -contains 'up' })
        Assert-Equal $upCalls.Count 1 'Compose up must happen once.'
        foreach ($record in @($configCalls[0], $upCalls[0])) {
            $call = $record.Arguments
            Assert-Equal $record.Builder 'desktop-linux' 'Builds must override any remote Buildx builder in this process.'
            Assert-Equal $record.Bake 'false' 'Alternate Compose Bake builds must be disabled for this local launch.'
            Assert-Equal $call[0] '--context' 'Subsequent Docker operations must pin the inspected context.'
            Assert-Equal $call[1] 'desktop-linux' 'Wrong Docker context was selected.'
            Assert-True ($call -contains (Join-Path $script:Scenario.Root '.env')) 'Compose must use the extracted folder env file.'
            Assert-True ($call -contains (Join-Path $script:Scenario.Root 'compose.yaml')) 'Compose must use the extracted folder manifest.'
            Assert-True ($call -contains 'boreal') 'Compose project must keep the stable Boreal volume identity.'
        }
        Assert-Equal $upCalls[0].Arguments[-1] 'web' 'Start only the web dependency graph, never optional verification profiles.'
        foreach ($flag in @('--build', '-d', '--wait', '--wait-timeout')) { Assert-True ($upCalls[0].Arguments -contains $flag) "Missing Compose readiness flag $flag." }
        Assert-True (-not $env:BOREAL_PORT -and -not $env:COMPOSE_PROFILES) 'Inherited settings must not silently override the local demo configuration.'
    }
    Test-Case 'unsafe published web ports and extra published services are rejected' {
        foreach ($mode in @('public', 'missing', 'multiple', 'wrong-target', 'zero', 'large', 'text', 'extra-service')) {
            New-Scenario
            Set-ExistingEnv
            switch ($mode) {
                'public' { $script:Scenario.Config.services.web.ports[0].host_ip = '0.0.0.0' }
                'missing' { $script:Scenario.Config.services.web.ports = @() }
                'multiple' { $script:Scenario.Config.services.web.ports += @{ host_ip = '127.0.0.1'; target = 8080; published = '9090' } }
                'wrong-target' { $script:Scenario.Config.services.web.ports[0].target = 8000 }
                'zero' { $script:Scenario.Config.services.web.ports[0].published = '0' }
                'large' { $script:Scenario.Config.services.web.ports[0].published = '65536' }
                'text' { $script:Scenario.Config.services.web.ports[0].published = 'not-a-number' }
                'extra-service' { $script:Scenario.Config.services.db.ports = @(@{ host_ip = '127.0.0.1'; target = 5432; published = '5432' }) }
            }
            Invoke-Scenario
            Assert-Failure
            Assert-NoStart
        }
    }
    Test-Case 'Compose startup errors preserve existing credentials and never poll or browse' {
        New-Scenario
        Set-ExistingEnv
        $path = Join-Path $script:Scenario.Root '.env'
        $before = Get-HexHash ([IO.File]::ReadAllBytes($path))
        $script:Scenario.FailOn = 'up --build'
        Invoke-Scenario
        Assert-Failure
        Assert-Equal $script:Scenario.HealthCalls 0 'Health must not be polled after Compose fails.'
        Assert-Equal (Get-HexHash ([IO.File]::ReadAllBytes($path))) $before 'Compose failure changed existing credentials.'
        Assert-True ($script:Captured -match 'Startup failed') 'Compose failure guidance was lost.'
    }
    Test-Case 'wrong or incomplete health response never opens a browser' {
        $invalidResponses = @(
            $null,
            [pscustomobject]@{},
            [pscustomobject]@{ status = 'error'; product = 'Boreal'; synthetic = $true; runtime = 'postgres' },
            [pscustomobject]@{ status = 'ok'; product = 'Other'; synthetic = $true; runtime = 'postgres' },
            [pscustomobject]@{ status = 'ok'; product = 'Boreal'; synthetic = $false; runtime = 'postgres' },
            [pscustomobject]@{ status = 'ok'; product = 'Boreal'; synthetic = 'true'; runtime = 'postgres' },
            [pscustomobject]@{ status = 'ok'; product = 'Boreal'; synthetic = 1; runtime = 'postgres' },
            [pscustomobject]@{ status = 'ok'; product = 'Boreal'; synthetic = $true; runtime = 'test-memory' }
        )
        foreach ($health in $invalidResponses) {
            New-Scenario
            Set-ExistingEnv
            $script:Scenario.Health = $health
            Invoke-Scenario
            Assert-Failure
            Assert-Equal $script:Scenario.HealthCalls 1 'A zero timeout must still perform exactly one health check.'
            Assert-True ($script:Captured -match 'health check timed out') 'Health timeout guidance was lost.'
        }
    }
    Test-Case 'health connection timeout never opens a browser' {
        New-Scenario
        Set-ExistingEnv
        $script:Scenario.HealthThrows = $true
        Invoke-Scenario
        Assert-Failure
        Assert-Equal $script:Scenario.HealthCalls 1 'Timeout should return promptly at zero deadline.'
    }
    Test-Case 'verified Boreal PostgreSQL health opens the browser once' {
        New-Scenario
        Set-ExistingEnv
        Invoke-Scenario
        Assert-Equal $script:Result 0 'Healthy Boreal should succeed.'
        Assert-Equal $script:Scenario.HealthCalls 1 'Ready service must not be repeatedly polled.'
        Assert-Equal $script:Scenario.BrowserUrls.Count 1 'Ready service must open one browser.'
        Assert-Equal $script:Scenario.BrowserUrls[0] 'http://127.0.0.1:8080' 'Unexpected default launch URL.'
    }
    Test-Case 'missing browser leaves a useful manual URL after a successful launch' {
        New-Scenario
        Set-ExistingEnv
        $script:Scenario.BrowserThrows = $true
        Invoke-Scenario
        Assert-Equal $script:Result 0 'A browser association problem must not mark a healthy stack as failed.'
        Assert-Equal $script:Scenario.BrowserUrls.Count 1 'Browser failures must not cause repeated launches.'
        Assert-True ($script:Captured -match 'http://127.0.0.1:8080') 'Manual browser URL missing.'
    }

    Test-Case 'native Docker boundary suppresses stderr and returns only a controlled failure' {
        $stub = Join-Path $script:TempRoot 'failing docker.cmd'
        $secret = 'private-native-output-do-not-print'
        [IO.File]::WriteAllText($stub, "@echo off`r`necho $secret`r`necho $secret 1>&2`r`nexit /b 37`r`n", [Text.Encoding]::ASCII)
        $script:Docker = $stub
        $script:NativeCaught = $null
        $captured = @(& {
            try { & $originalInvokeDocker @('version') 'Safe Docker failure.' }
            catch { $script:NativeCaught = $_ }
        } *>&1) | Out-String
        Assert-True ($null -ne $script:NativeCaught) 'Nonzero native Docker result must fail.'
        Assert-Equal $script:NativeCaught.Exception.Message 'Safe Docker failure.' 'Native Docker error exposed raw output.'
        Assert-Equal $script:NativeCaught.Exception.Data['BorealSafe'] $true 'Native failure lost the controlled error marker.'
        Assert-True (-not $captured.Contains($secret)) 'Native stdout/stderr leaked on failure.'
    }

    Test-Case 'actual cmd.exe handles quoted extracted paths with both CRLF and LF launcher files' {
        Assert-True ($env:OS -eq 'Windows_NT') 'Native cmd.exe smoke must run on Windows.'
        $original = [IO.File]::ReadAllText($LauncherPath).Replace("`r`n", "`n")
        foreach ($lineEnding in @('CRLF', 'LF')) {
            $root = Join-Path $script:TempRoot ('cmd smoke & (100%) ! and apostrophe''s ' + $lineEnding)
            [void][IO.Directory]::CreateDirectory($root)
            # Omit compose.yaml deliberately: fail before any Docker discovery.
            # Docker can exist in System32 on CI even with a restricted PATH.
            $path = Join-Path $root 'start-boreal.cmd'
            $source = $original
            if ($lineEnding -eq 'CRLF') { $source = $source.Replace("`n", "`r`n") }
            [IO.File]::WriteAllText($path, $source, [Text.Encoding]::ASCII)
            $startInfo = New-Object Diagnostics.ProcessStartInfo
            $startInfo.FileName = Join-Path $env:SystemRoot 'System32\cmd.exe'
            $startInfo.Arguments = '/d /s /c ""' + $path + '""'
            # Different cwd ensures %~dp0, rather than current directory, is used.
            $startInfo.WorkingDirectory = $script:TempRoot
            $startInfo.UseShellExecute = $false
            $startInfo.CreateNoWindow = $true
            $startInfo.RedirectStandardInput = $true
            $startInfo.RedirectStandardOutput = $true
            $startInfo.RedirectStandardError = $true
            # Only Windows tools are needed; incomplete extraction stops before Docker.
            $startInfo.EnvironmentVariables['PATH'] = (Join-Path $env:SystemRoot 'System32') + ';' + (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0')
            $process = New-Object Diagnostics.Process
            $process.StartInfo = $startInfo
            $started = $false
            try {
                $started = $process.Start()
                Assert-True $started 'Could not launch cmd.exe.'
                $stdout = $process.StandardOutput.ReadToEndAsync()
                $stderr = $process.StandardError.ReadToEndAsync()
                $process.StandardInput.WriteLine('x')
                $process.StandardInput.Close()
                if (-not $process.WaitForExit(60000)) {
                    Stop-NativeTestProcess $process
                    throw "Native $lineEnding smoke exceeded its 60-second startup allowance."
                }
                $output = $stdout.Result + $stderr.Result
                Assert-Equal $process.ExitCode 1 "Native $lineEnding launcher should return its incomplete-extraction failure code."
                Assert-True ($output -match 'Boreal could not start:.*Extract the entire ZIP') "Native $lineEnding command did not reach the controlled extraction check: $output"
                Assert-True ($output -notmatch 'ParserError|MissingEndCurlyBrace|Unexpected token|not recognized as an internal') "Native $lineEnding command quoting failed: $output"
                Assert-True (-not (Test-Path -LiteralPath (Join-Path $root '.env'))) 'Native preflight failure created credentials.'
            } finally {
                if ($started) { Stop-NativeTestProcess $process }
                $process.Dispose()
            }
        }
    }
} finally {
    if ($null -ne $savedEnvironment) {
        foreach ($name in $savedEnvironment.Keys) { [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process') }
    }
    if (Test-Path -LiteralPath $script:TempRoot) {
        try { Remove-Item -LiteralPath $script:TempRoot -Recurse -Force }
        catch {
            $script:Failed++
            Write-Host ('FAIL: test folder cleanup -- ' + $_.Exception.Message)
        }
    }
}

Write-Host ("Windows launcher tests: {0} passed; {1} failed." -f $script:Passed, $script:Failed)
if ($script:Failed) { exit 1 }
# Clear the exit code left by deliberate native-command failure tests.
exit 0
