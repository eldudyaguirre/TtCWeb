$ErrorActionPreference = "Stop"
$ProjectDir = "D:\Aplicaciones\TtcWeb"
$PythonCommand = "poetry run python manage.py iess_rdep_worker --interval 5"
Set-Location $ProjectDir
& powershell.exe -NoProfile -Command $PythonCommand
