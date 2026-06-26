# backup_remoto.ps1 — copia la DB de producción (Fly.io) a esta PC.
# Premortem #3, R1: la DB y sus backups viven en UN solo volumen de Fly;
# este script crea la copia EXTERNA que falta. Programalo diario con el
# Programador de tareas de Windows (ver RUNBOOK-OPERACION.md).
#
# Requisitos: flyctl instalado y logueado (fly auth login).
# Uso manual:  powershell -ExecutionPolicy Bypass -File scripts\backup_remoto.ps1

param(
    [string]$App = "radar-financiero",
    [string]$Destino = "$PSScriptRoot\..\backups-remotos",
    [int]$RetencionDias = 90
)

$ErrorActionPreference = "Stop"
$fecha = Get-Date -Format "yyyyMMdd-HHmmss"
New-Item -ItemType Directory -Force -Path $Destino | Out-Null
$archivo = Join-Path $Destino "finanzas-cloud-$fecha.db"

# 1. Despertar la máquina (auto_stop): un GET al health endpoint la inicia.
try {
    Invoke-WebRequest -Uri "https://$App.fly.dev/_stcore/health" -TimeoutSec 60 -UseBasicParsing | Out-Null
    Start-Sleep -Seconds 5
} catch {
    Write-Warning "No se pudo despertar la app via HTTP; intento sftp igual."
}

# 2. Descargar la DB.
fly ssh sftp get /app/data/finanzas.db $archivo -a $App
if (-not (Test-Path $archivo) -or (Get-Item $archivo).Length -lt 1024) {
    Write-Error "FALLO el backup remoto: el archivo no se descargo o esta vacio."
    exit 1
}

# 3. Verificar integridad y contar transacciones (un backup corrupto no es backup).
$check = python -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); n=c.execute('SELECT COUNT(*) FROM transacciones').fetchone()[0]; ok=c.execute('PRAGMA integrity_check').fetchone()[0]; print(f'{n}|{ok}')" $archivo
$partes = $check.Split("|")
if ($partes[1] -ne "ok" -or [int]$partes[0] -lt 1) {
    Write-Error "El backup descargado NO pasa integrity_check o tiene 0 transacciones: $check"
    exit 1
}
Write-Host "OK: backup en $archivo ($($partes[0]) transacciones, integrity=$($partes[1]))"

# 4. Purga local: borrar copias remotas con mas de $RetencionDias dias.
Get-ChildItem $Destino -Filter "finanzas-cloud-*.db" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$RetencionDias) } |
    Remove-Item -Force

exit 0
