param(
    [string[]]$Tasks = @('assembleDebug', 'testDebugUnitTest', 'lintDebug')
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$studioJava = 'C:\Program Files\Android\Android Studio\jbr'
if (Test-Path -LiteralPath "$studioJava\bin\java.exe") { $env:JAVA_HOME = $studioJava }
$env:GRADLE_USER_HOME = Join-Path $PSScriptRoot '.gradle-user-home'
$env:ANDROID_USER_HOME = Join-Path $PSScriptRoot '.android-user-home'
if (-not (Test-Path -LiteralPath 'local.properties')) {
    $sdkPath = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
    if (-not (Test-Path -LiteralPath "$sdkPath\platforms")) {
        throw 'SDK introuvable. Terminer la configuration Android Studio, ou renseigner local.properties.'
    }
    $sdkProperty = 'sdk.dir=' + $sdkPath.Replace('\', '/').Replace(':', '\:')
    [IO.File]::WriteAllText((Join-Path $PSScriptRoot 'local.properties'), $sdkProperty + "`n")
}
$debugKey = Join-Path $env:USERPROFILE '.android\debug.keystore'
$buildArguments = @($Tasks) + @('--console=plain')
if (Test-Path -LiteralPath $debugKey) {
    $buildArguments += "-PdebugKeystore=$debugKey"
}
& .\gradlew.bat @buildArguments
exit $LASTEXITCODE
