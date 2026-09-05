$root = $PSScriptRoot
$output = Join-Path $root "source.zip"

$files = @(
    Join-Path $root "main.py"
    Join-Path $root "requirements.txt"
)

$files += Get-ChildItem -Path (Join-Path $root "src") -Recurse -File |
    Where-Object { $_.FullName -notlike "*\__pycache__\*" } |
    Select-Object -ExpandProperty FullName

if (Test-Path $output) {
    Remove-Item $output
}

Compress-Archive -Path $files -DestinationPath $output
Write-Output "Created source.zip"