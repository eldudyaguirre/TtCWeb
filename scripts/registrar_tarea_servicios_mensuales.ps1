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

# Priorizar el intérprete del entorno administrado por Poetry.
$PythonPath = $null
$PoetryCommand = Get-Command poetry.exe -ErrorAction SilentlyContinue
if (-not $PoetryCommand) {
    $PoetryCommand = Get-Command poetry -ErrorAction SilentlyContinue
}
if ($PoetryCommand) {
    $PoetryPython = (& $PoetryCommand.Source env info --executable 2>$null | Select-Object -First 1)
    if ($PoetryPython) {
        $PoetryPython = $PoetryPython.Trim()
        if (Test-Path $PoetryPython) {
            $PythonPath = $PoetryPython
        }
    }
}

# Compatibilidad con entornos virtuales convencionales del proyecto.
if (-not $PythonPath) {
    $PythonCandidates = @(
        (Join-Path $ProjectRoot ".venv\Scripts\python.exe"),
        (Join-Path $ProjectRoot "venv\Scripts\python.exe")
    )
    $PythonPath = $PythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}

if (-not $PythonPath) {
    throw "No se encontró el Python del entorno virtual de TtCWeb. Ejecuta 'poetry install' y verifica 'poetry env info --executable'. No se usará el Python global para evitar ejecutar la tarea sin Django."
}

Write-Host "Proyecto: $ProjectRoot"
Write-Host "Python:   $PythonPath"
Write-Host "Tarea:    $TaskName"
Write-Host "Horario:  dia 1 de cada mes, 06:00 (hora local del servidor)"
Write-Host "La cuenta elegida debe tener acceso al proyecto, al archivo .env y a BdTotal."

# El cmdlet New-ScheduledTaskTrigger no ofrece -Monthly en todas las versiones
# de Windows PowerShell. Se registra un CalendarTrigger mensual mediante XML.
$Credential = Get-Credential -UserName $RunAsUser -Message "Credenciales de la cuenta que ejecutará TtCWeb automáticamente"

$NextRun = (Get-Date).Date.AddHours(6)
$FirstDayThisMonth = Get-Date -Year $NextRun.Year -Month $NextRun.Month -Day 1 -Hour 6 -Minute 0 -Second 0
if ($FirstDayThisMonth -le (Get-Date)) {
    $NextMonth = (Get-Date -Day 1).AddMonths(1)
    $FirstDayThisMonth = Get-Date -Year $NextMonth.Year -Month $NextMonth.Month -Day 1 -Hour 6 -Minute 0 -Second 0
}
$StartBoundary = $FirstDayThisMonth.ToString("yyyy-MM-ddTHH:mm:ss")

$EscapedPython = [System.Security.SecurityElement]::Escape($PythonPath)
$EscapedManage = [System.Security.SecurityElement]::Escape($ManagePath)
$EscapedWorkingDirectory = [System.Security.SecurityElement]::Escape($ProjectRoot)
$EscapedUser = [System.Security.SecurityElement]::Escape($Credential.UserName)

$TaskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Genera automáticamente los servicios contables del mes anterior en TtCWeb.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>$StartBoundary</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByMonth>
        <DaysOfMonth><Day>1</Day></DaysOfMonth>
        <Months>
          <January/><February/><March/><April/><May/><June/>
          <July/><August/><September/><October/><November/><December/>
        </Months>
      </ScheduleByMonth>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$EscapedUser</UserId>
      <LogonType>Password</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <Enabled>true</Enabled>
    <ExecutionTimeLimit>PT1H</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$EscapedPython</Command>
      <Arguments>"$EscapedManage" generar_servicios_mensuales</Arguments>
      <WorkingDirectory>$EscapedWorkingDirectory</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

$Password = $Credential.GetNetworkCredential().Password
Register-ScheduledTask -TaskName $TaskName -Xml $TaskXml -User $Credential.UserName -Password $Password -Force | Out-Null

Write-Host ""
Write-Host "Tarea programada registrada correctamente." -ForegroundColor Green
Write-Host "Proxima ejecucion programada: $StartBoundary"
Write-Host "Prueba de consulta (no inserta datos):"
Write-Host ('"{0}" "{1}" generar_servicios_mensuales --dry-run' -f $PythonPath, $ManagePath)
Write-Host ""
Write-Host "El resultado de cada ejecución se guardará en:"
Write-Host (Join-Path $ProjectRoot 'logs\servicios_mensuales.log')
