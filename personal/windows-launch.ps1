param([string]$Executable, [string]$Project = '')
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if ($Project) {
  Start-Process -FilePath $Executable -ArgumentList ('--project "' + $Project + '"') | Out-Null
} else {
  Start-Process -FilePath $Executable | Out-Null
}
