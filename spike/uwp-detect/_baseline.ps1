$ErrorActionPreference = 'SilentlyContinue'
$apps = @()
foreach ($pkg in Get-AppxPackage) {
    if ($pkg.IsFramework) { continue }
    try {
        $manifest = Get-AppxPackageManifest $pkg
        foreach ($appId in $manifest.Package.Applications.Application.Id) {
            $displayName = $manifest.Package.Properties.DisplayName
            $exe = $manifest.Package.Applications.Application.Executable

            if ([string]::IsNullOrWhiteSpace($exe) -or $exe -eq 'GameLaunchHelper.exe') {
                $configPath = Join-Path $pkg.InstallLocation 'MicrosoftGame.Config'
                if (Test-Path $configPath) {
                    [xml]$gc = Get-Content $configPath
                    $exe = $gc.Game.ExecutableList.Executable.Name
                    if ($exe -is [Object[]]) { $exe = $exe[0].ToString() }
                } else {
                    continue
                }
            }

            if ($displayName -like '*ms-resource*' -or $displayName -like '*DisplayName*') {
                continue
            }

            $logo = ''
            $vis = $manifest.Package.Applications.Application.VisualElements
            if ($vis.Square150x150Logo) {
                $logo = Join-Path $pkg.InstallLocation $vis.Square150x150Logo
            }

            $aumid = $pkg.PackageFamilyName + '!' + $appId
            $installDir = $pkg.InstallLocation
            $isGame = Test-Path (Join-Path $pkg.InstallLocation 'MicrosoftGame.Config')

            $apps += @{
                Name = $displayName
                AUMID = $aumid
                Family = $pkg.PackageFamilyName
                PackageName = $pkg.Name
                Exe = $exe
                Logo = $logo
                InstallLocation = $installDir
                IsGame = $isGame
            }
        }
    } catch {}
}
$apps | ConvertTo-Json -Depth 3
