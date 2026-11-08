<#
Copies the search data from this PC to the server: backend/chroma_db (the
vector embeddings), backend/lexical.db (the keyword index) and backend/uploads
(the PDFs, avatars, blog covers).

These are not in git (742 MB; the repository is public, and they hold the full
text of every judgment), so `git push` does not carry them. They do not need
to: on the server they live outside the image (docker-compose.yml), and every
later `git pull` + `docker compose up -d --build` keeps them. Run this:

  * once, before the first `docker compose up` on a new server, and
  * again only if you ingest PDFs on this PC instead of on the server's admin page.

It REPLACES the server's chroma_db and lexical.db with this PC's copy, so PDFs
uploaded on the server since the last copy would drop out of search. The
server's previous copy is moved to ~/search-data-backups/<time>/ (the newest
two are kept), so a mistake can be undone. uploads/ is merged, never deleted.

The search data and MongoDB must match (they describe the same judgments):
copy the database to Atlas from the same moment, with the backend stopped.

Usage (from the project folder, with the backend on this PC STOPPED):
  powershell -ExecutionPolicy Bypass -File deploy\sync_search_data.ps1 `
      -Server ubuntu@<server-ip> -KeyFile C:\path\to\oracle-key.key
#>
param(
    [Parameter(Mandatory = $true)][string]$Server,     # user@host, e.g. ubuntu@203.0.113.7
    [Parameter(Mandatory = $true)][string]$KeyFile,    # the SSH private key Oracle gave you
    [string]$RemoteDir = "legal-hybrid-rag",           # the git clone, relative to the server user's home
    [switch]$Yes                                       # skip the confirmation question
)
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
foreach ($item in @("chroma_db", "lexical.db")) {
    if (-not (Test-Path (Join-Path $backend $item))) { throw "backend\$item not found: nothing to copy." }
}
if (-not (Test-Path $KeyFile)) { throw "Key file not found: $KeyFile" }
foreach ($tool in @("ssh", "scp", "tar")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool is not installed (Windows 10/11 include it: Settings > Optional features > OpenSSH Client)." }
}

# A copy taken while the backend or an ingestion run is writing can be half-written.
$busy = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -match "uvicorn|main\.py|ingest|reindex" }
if ($busy) {
    $busy | ForEach-Object { Write-Host "  running: $($_.CommandLine)" }
    throw "Stop the backend / ingestion on this PC first, so the search data is not copied mid-write."
}

$remoteDate = (& ssh -i $KeyFile -o BatchMode=yes $Server "stat -c %y $RemoteDir/backend/lexical.db 2>/dev/null || echo none").Trim()
if ($LASTEXITCODE -ne 0) { throw "Could not connect to $Server over SSH." }
$localDate = (Get-Item (Join-Path $backend "lexical.db")).LastWriteTime.ToString("yyyy-MM-dd HH:mm")
Write-Host "Search data on this PC:     $localDate"
Write-Host "Search data on the server:  $remoteDate"
if (-not $Yes) {
    $answer = Read-Host "Replace the server's search data with this PC's? (yes/no)"
    if ($answer -ne "yes") { Write-Host "Nothing copied."; exit 1 }
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$archive = Join-Path $env:TEMP "search-data-$stamp.tar.gz"
Write-Host "Packing chroma_db, lexical.db and uploads..."
$parts = @("chroma_db", "lexical.db")
if (Test-Path (Join-Path $backend "uploads")) { $parts += "uploads" }
& tar -czf $archive -C $backend @parts
if ($LASTEXITCODE -ne 0) { throw "tar failed." }
Write-Host ("  {0:N0} MB" -f ((Get-Item $archive).Length / 1MB))

try {
    Write-Host "Uploading (this takes a while)..."
    & scp -i $KeyFile $archive "${Server}:/tmp/search-data-$stamp.tar.gz"
    if ($LASTEXITCODE -ne 0) { throw "Upload failed; the server was not changed." }

    # Run on the server. Sent base64-encoded: PowerShell would otherwise add
    # Windows line endings that bash cannot run.
    $remote = @'
set -e
stamp="$1"; dir="$HOME/$2"; archive="/tmp/search-data-$stamp.tar.gz"
mkdir -p "$dir/backend"
cd "$dir"
running=0
if docker compose ps --status running --services 2>/dev/null | grep -qx backend; then
    running=1
    echo "Stopping the backend..."
    docker compose stop backend
fi
keep="$HOME/search-data-backups/$stamp"
mkdir -p "$keep"
[ -e backend/chroma_db ] && mv backend/chroma_db "$keep/"
[ -e backend/lexical.db ] && mv backend/lexical.db "$keep/"
if ! tar -xzf "$archive" -C backend; then
    echo "Unpacking failed: putting the previous search data back."
    rm -rf backend/chroma_db backend/lexical.db
    [ -e "$keep/chroma_db" ] && mv "$keep/chroma_db" backend/
    [ -e "$keep/lexical.db" ] && mv "$keep/lexical.db" backend/
    rmdir "$keep" 2>/dev/null || true
    rm -f "$archive"
    [ "$running" = 1 ] && docker compose start backend
    exit 1
fi
rm -f "$archive"
rmdir "$keep" 2>/dev/null || echo "Previous search data kept in $keep"
ls -1dt "$HOME"/search-data-backups/*/ 2>/dev/null | tail -n +3 | xargs -r rm -rf
if [ "$running" = 1 ]; then
    echo "Starting the backend..."
    docker compose start backend
fi
echo "Done: $(du -sh backend/chroma_db | cut -f1) vector store, $(du -sh backend/lexical.db | cut -f1) keyword index."
'@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remote.Replace("`r", "")))
    & ssh -i $KeyFile $Server "echo $encoded | base64 -d | bash -s -- $stamp $RemoteDir"
    if ($LASTEXITCODE -ne 0) { throw "The server could not install the search data (see above)." }
}
finally {
    Remove-Item $archive -ErrorAction SilentlyContinue
}
Write-Host "Search data is on the server. Check: curl http://127.0.0.1:8001/api/health (on the server)."
