param(
    [string]$InputPath = "WoWCombatLog.txt",
    [string]$OutputPath = "WoWCombatLog_Cleaned.txt"
)

if (-not (Test-Path $InputPath)) {
    Write-Error "Input file not found: $InputPath"
    exit
}

Write-Host "Processing $InputPath..." -ForegroundColor Cyan

# Pattern explanation:
# 1. (Player-[^,]+) -> Matches the Player GUID field (e.g., Player-1-00002CA0)
# 2. ,                -> The comma separating the GUID and the name
# 3. "([^"]+)-"       -> The quoted name containing a trailing hyphen, captured as group 2
# Replacement uses $1 (the GUID) and $2 (the name without the hyphen)
$pattern = '(Player-[^,]+),"([^"]+)-"'
$replacement = '$1,"$2"'

# Read line-by-line to handle huge log files efficiently
Get-Content -Path $InputPath | ForEach-Object {
    [System.Text.RegularExpressions.Regex]::Replace($_, $pattern, $replacement)
} | Set-Content -Path $OutputPath -Encoding UTF8

Write-Host "Done! Cleaned log saved to: $OutputPath" -ForegroundColor Green