# Jarvis — Windows Speech Recognition (System.Speech) for Listen / diagnose.
# Invoked with: powershell -NoProfile -ExecutionPolicy Bypass -File windows_listen.ps1
# Prefer -File (not -Command) so quoting stays simple.
param(
    [double]$TimeoutSeconds = 15,
    [switch]$ProbeOnly
)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

function Write-Status([string]$Status, [string]$Text = '', [string]$ErrorMsg = '') {
    Write-Output ("JARVIS_SR_STATUS=" + $Status)
    if ($Text -ne '') { Write-Output ("JARVIS_SR_TEXT=" + $Text) }
    if ($ErrorMsg -ne '') { Write-Output ("JARVIS_SR_ERROR=" + $ErrorMsg) }
}

try {
    Add-Type -AssemblyName System.Speech | Out-Null
} catch {
    Write-Status 'unavailable' -ErrorMsg ("Add-Type System.Speech failed: " + $_.Exception.Message)
    exit 2
}

$engine = $null
try {
    # Prefer en-GB then en-US culture when installed; else OS default.
    $cultureNames = @('en-GB', 'en-US')
    foreach ($name in $cultureNames) {
        try {
            $ci = [System.Globalization.CultureInfo]::GetCultureInfo($name)
            $engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine $ci
            break
        } catch {
            $engine = $null
        }
    }
    if ($null -eq $engine) {
        $engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine
    }

    # Explicit default capture device (shared mode) — fails clearly if privacy/device broken.
    try {
        $engine.SetInputToDefaultAudioDevice()
    } catch {
        $msg = $_.Exception.Message
        $st = 'mic'
        if ($msg -match '(?i)denied|permission|access|privacy') { $st = 'denied' }
        Write-Status $st -ErrorMsg $msg
        exit 3
    }

    if ($ProbeOnly) {
        $probe = 'ready'
        try {
            $cult = $engine.RecognizerInfo.Culture.Name
            if ($cult) { $probe = "ready;culture=$cult" }
        } catch {}
        Write-Status 'ok'
        Write-Output ("JARVIS_SR_PROBE=" + $probe)
        exit 0
    }

    $grammar = New-Object System.Speech.Recognition.DictationGrammar
    $engine.LoadGrammar($grammar)

    $ts = [TimeSpan]::FromSeconds([Math]::Max(1.0, [double]$TimeoutSeconds))
    $result = $engine.Recognize($ts)

    if ($null -eq $result) {
        Write-Status 'timeout'
        exit 1
    }

    $text = [string]$result.Text
    if ([string]::IsNullOrWhiteSpace($text)) {
        Write-Status 'empty'
        exit 1
    }

    Write-Status 'ok' -Text $text.Trim()
    exit 0
} catch {
    $msg = $_.Exception.Message
    $st = 'error'
    if ($msg -match '(?i)denied|permission|access|privacy') { $st = 'denied' }
    elseif ($msg -match '(?i)device|microphone|audio|input') { $st = 'mic' }
    Write-Status $st -ErrorMsg $msg
    exit 3
} finally {
    if ($null -ne $engine) {
        try { $engine.Dispose() } catch {}
    }
}
