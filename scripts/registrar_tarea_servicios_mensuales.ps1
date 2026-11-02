[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$TaskName = "TtCWeb - Generar servicios mensuales",
    [string]$RunAsUser = "$env:USERDOMAIN\$env:USERNAME"
)

$ErrorActionPreference = "Stop"
$ZonaEcuador = "SA Pacific Standard Time"
$ZonaServidor = [System.TimeZoneInfo]::Local.Id
if ($ZonaServidor -ne $ZonaEcuador) {
    throw "La zona horaria de Windows es '$ZonaServidor'. Configura el servidor en '$ZonaEcuador' (Ecuador, UTC-05:00) antes de registrar la tarea para garantizar las 06:00 de Ecuador."
}

$ProjectRoot = (Resolve-Path $ProjectRoot).Path
$ManagePath = Join-Path $ProjectRoot "manage.py"

if (-not (Test-Path $ManagePath)) {
    throw "No se encontró manage.py en: $ProjectRoot"
}

$PythonCandidates = @(
    (Join-Path $ProjectRoot ".venv\Scripts\python.exe"),
    (Join-Path $ProjectRoot "venv\Scripts\python.exe")
)
$PythonPath = $PythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $PythonPath) {
    $PythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($PythonCommand) {
        $PythonPath = $PythonCommand.Source
    }
}
if (-not $PythonPath) {
    throw "No se encontró Python. Revisa la ruta del entorno virtual del proyecto."
}

Write-Host "Proyecto: $ProjectRoot"
Write-Host "Python:   $PythonPath"
Write-Host "Tarea:    $TaskName"
Write-Host "Horario:  día 1 de cada mes, 06:00 (hora local del servidor)"
Write-Host "La cuenta elegida debe tener acceso al proyecto, al archivo .env y a BdTotal."

$Credential = Get-Credential -UserName $RunAsUser -Message "Credenciales de la cuenta que ejecutará TtCWeb automáticamente"
$Action = New-ScheduledTaskAction -Execute $PythonPath -Argument ('"{0}" generar_servicios_mensuales' -f $ManagePath) -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Monthly -DaysOfMonth 1 -At "06:00"
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$Password = $Credential.GetNetworkCredential().Password

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -User $Credential.UserName -Password $Password -RunLevel Highest -Force | Out-Null

Write-Host ""
Write-Host "Tarea programada registrada correctamente." -ForegroundColor Green
Write-Host "Prueba de consulta (no inserta datos):"
Write-Host ('{0} manage.py generar_servicios_mensuales --dry-run' -f $PythonPath)
Write-Host ""
Write-Host "El resultado de cada ejecución se guardará en:"
Write-Host (Join-Path $ProjectRoot 'logs\servicios_mensuales.log')
