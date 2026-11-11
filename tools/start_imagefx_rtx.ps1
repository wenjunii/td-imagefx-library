param(
    [string]$Project = (Join-Path $PSScriptRoot '../TD_ImageFX_Library.toe'),
    [string]$TouchDesigner = 'C:\Program Files\Derivative\TouchDesigner\bin\TouchDesigner.exe',
    [string]$GpuName = 'RTX 3080 Ti'
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Project -PathType Leaf)) { throw "Project not found: $Project" }
if (-not (Test-Path -LiteralPath $TouchDesigner -PathType Leaf)) { throw "TouchDesigner not found: $TouchDesigner" }
$gpus = @(& nvidia-smi --query-gpu=name,pci.bus_id --format=csv,noheader)
if ($LASTEXITCODE -ne 0) { throw 'Unable to query NVIDIA GPU bus IDs' }
$match = @($gpus | Where-Object { $_.Split(',')[0].Contains($GpuName) })
if ($match.Count -ne 1) { throw "Expected one NVIDIA device matching '$GpuName'; found $($match.Count)" }
$bus = $match[0].Split(',')[1].Trim()
if ($bus -notmatch '^([0-9A-Fa-f]+):([0-9A-Fa-f]+):([0-9A-Fa-f]+)\.([0-9A-Fa-f]+)$') { throw "Unexpected bus ID: $bus" }
$affinity = (1..4 | ForEach-Object { [Convert]::ToInt32($Matches[$_],16) }) -join ':'
$file = (Resolve-Path -LiteralPath $Project).Path
Write-Host "Starting ImageFX on $($match[0].Split(',')[0]) (GPU bus $affinity)"
# This is the user's interactive editor, not a hidden background helper.
Start-Process -FilePath $TouchDesigner -ArgumentList @('-gpubusid', $affinity, ('"' + $file + '"'))
