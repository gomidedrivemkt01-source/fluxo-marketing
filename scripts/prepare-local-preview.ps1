param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$previewRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $previewRoot
$runtimeRoot = Join-Path $previewRoot '.preview\runtime'
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null

if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível criar o ambiente Python 3.12+.' }
}
& .\.venv\Scripts\python.exe -m pip install -e './backend[dev]'
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar as dependências do backend.' }

$pgExecutable = Join-Path $runtimeRoot 'pgsql\bin\postgres.exe'
if (-not (Test-Path -LiteralPath $pgExecutable)) {
    $package = Join-Path $runtimeRoot 'postgresql-17.11-3-windows-x64-binaries.zip'
    & curl.exe --http1.1 --location --fail --continue-at - --retry 8 --retry-all-errors --retry-delay 1 --silent --show-error --output $package 'https://get.enterprisedb.com/postgresql/postgresql-17.11-3-windows-x64-binaries.zip'
    if ($LASTEXITCODE -ne 0) { throw 'Falha no download do PostgreSQL portátil.' }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($package)
    try {
        foreach ($entry in $archive.Entries) {
            if ($entry.FullName -notmatch '^pgsql/(bin|lib|share)/' -or $entry.FullName.EndsWith('/')) { continue }
            $target = [System.IO.Path]::GetFullPath((Join-Path $runtimeRoot $entry.FullName))
            $expected = [System.IO.Path]::GetFullPath($runtimeRoot).TrimEnd('\') + '\'
            if (-not $target.StartsWith($expected, [StringComparison]::OrdinalIgnoreCase)) { throw 'Entrada fora do runtime.' }
            [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($target)) | Out-Null
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $true)
        }
    } finally { $archive.Dispose() }
}

Push-Location frontend
try {
    & npm.cmd ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar as dependências do frontend.' }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Falha no build do frontend.' }
} finally { Pop-Location }

& .\.venv\Scripts\python.exe scripts/local_preview.py init
if ($LASTEXITCODE -ne 0) { throw 'Falha na preparação do banco local.' }
