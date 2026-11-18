$ErrorActionPreference = "Stop"
$ProjectDir = "D:\Aplicaciones\TtcWeb"
$Script = Join-Path $ProjectDir "scripts\iniciar_iess_rdep_worker.ps1"
$TaskName = "TtCWeb - IESS RDEP Worker"
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Script`"" -WorkingDirectory $ProjectDir
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $User
$Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Highest
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$Task = New-ScheduledTask -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description "Worker de consultas de planillas IESS para RDEP en TotalCounts."
Register-ScheduledTask -TaskName $TaskName -InputObject $Task -Force | Out-Null
Write-Host "Tarea instalada: $TaskName"
Write-Host "Iniciar: Start-ScheduledTask -TaskName `"$TaskName`""
