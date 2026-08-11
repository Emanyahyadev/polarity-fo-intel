$base = "D:\Projects\Polarity IQ Stage 2\family_office_discovery"
$dataDir = Join-Path $base "data"
$outDir = Join-Path $base "output"
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }

$all = New-Object System.Collections.Generic.List[object]
$malformed = 0
$skipped = 0
$cycleFiles = Get-ChildItem (Join-Path $dataDir "cycle*.jsonl") | Sort-Object Name

$badLines = New-Object System.Collections.Generic.List[string]

foreach ($f in $cycleFiles) {
    $cycle = [System.IO.Path]::GetFileNameWithoutExtension($f.Name)
    $lines = Get-Content $f.FullName
    foreach ($line in $lines) {
        $t = $line.Trim()
        if ($t -eq "") { continue }
        try {
            $obj = $t | ConvertFrom-Json
            if (-not $obj.candidate_name) { $skipped++; continue }
            $obj | Add-Member -NotePropertyName "discovery_cycle" -NotePropertyValue $cycle -Force
            $obj | Add-Member -NotePropertyName "raw_line" -NotePropertyValue $t -Force
            $all.Add($obj)
        } catch {
            $malformed++
            $badLines.Add($t)
        }
    }
}

"Parsed: $($all.Count) | Malformed: $malformed | Skipped (no name): $skipped"

$seen = @{}
$deduped = New-Object System.Collections.Generic.List[object]
$dupes = 0
foreach ($c in $all) {
    $key = ($c.candidate_name -replace '\s+', ' ').Trim().ToLower()
    if ($seen.ContainsKey($key)) {
        $dupes++
        continue
    }
    $seen[$key] = $true
    $deduped.Add($c)
}
"Dupes removed: $dupes | Unique: $($deduped.Count)"

$master = Join-Path $outDir "master_candidates.jsonl"
$deduped | ForEach-Object {
    $clean = [PSCustomObject]@{
        candidate_name = $_.candidate_name
        possible_type  = $_.possible_type
        country        = $_.country
        city           = $_.city
        website        = $_.website
        discovery_source = $_.discovery_source
        discovery_reason = $_.discovery_reason
        discovery_cycle  = $_.discovery_cycle
    }
    $clean | ConvertTo-Json -Compress
} | Set-Content -Encoding UTF8 $master
"Master written: $master"

"`n=== By country ==="
$deduped | Group-Object country | Sort-Object Count -Descending | ForEach-Object { "{0,4}  {1}" -f $_.Count, $_.Name }

"`n=== By type ==="
$deduped | Group-Object possible_type | Sort-Object Count -Descending | ForEach-Object { "{0,4}  {1}" -f $_.Count, $_.Name }

"`n=== By cycle ==="
$deduped | Group-Object discovery_cycle | Sort-Object Name | ForEach-Object { "{0,4}  {1}" -f $_.Count, $_.Name }

if ($malformed -gt 0) {
    $badFile = Join-Path $outDir "malformed_lines.txt"
    $badLines | Set-Content -Encoding UTF8 $badFile
    "`nMalformed lines written: $badFile"
}