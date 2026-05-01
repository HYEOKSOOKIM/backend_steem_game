$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$backendDir = Join-Path $repoRoot "backend"
$dataRoot = Join-Path $backendDir "data\report"
$batchRoot = Join-Path $dataRoot "batch_runs"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runDir = Join-Path $batchRoot "run-$timestamp"
$logPath = Join-Path $runDir "batch.log"
$summaryPath = Join-Path $runDir "summary.json"
$statePath = Join-Path $runDir "state.json"
$gameLogDir = Join-Path $runDir "games"

New-Item -ItemType Directory -Force -Path $runDir | Out-Null
New-Item -ItemType Directory -Force -Path $gameLogDir | Out-Null

function Write-BatchLog {
  param(
    [Parameter(Mandatory = $true)][string]$Message
  )

  $line = "[$(Get-Date -Format s)] $Message"
  $line | Tee-Object -FilePath $logPath -Append
}

function Write-State {
  param(
    [Parameter(Mandatory = $true)]$State
  )

  $State | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $statePath
}

$games = @(
  @{ appid = 1145350; name = "Hades II" },
  @{ appid = 553850; name = "HELLDIVERS 2" },
  @{ appid = 413150; name = "Stardew Valley" },
  @{ appid = 1623730; name = "Palworld" },
  @{ appid = 2246340; name = "Monster Hunter Wilds" },
  @{ appid = 949230; name = "Cities: Skylines" },
  @{ appid = 2483190; name = "Forza Horizon" },
  @{ appid = 814380; name = "Sekiro" },
  @{ appid = 230410; name = "Warframe" },
  @{ appid = 1085660; name = "Destiny 2" },
  @{ appid = 2909400; name = "Final Fantasy" },
  @{ appid = 2054970; name = "Dragon's Dogma 2" },
  @{ appid = 550; name = "Left 4 Dead 2" },
  @{ appid = 730; name = "Counter-Strike" },
  @{ appid = 1172470; name = "Apex Legends" },
  @{ appid = 359550; name = "Rainbow Six Siege" },
  @{ appid = 440; name = "Team Fortress 2" },
  @{ appid = 2357570; name = "Overwatch" },
  @{ appid = 2000950; name = "Call of Duty" },
  @{ appid = 570; name = "Dota 2" },
  @{ appid = 427520; name = "Factorio" },
  @{ appid = 294100; name = "RimWorld" },
  @{ appid = 394360; name = "Hearts of Iron IV" },
  @{ appid = 236850; name = "Europa Universalis IV" },
  @{ appid = 1158310; name = "Crusader Kings III" },
  @{ appid = 526870; name = "Satisfactory" },
  @{ appid = 108600; name = "Project Zomboid" },
  @{ appid = 2537590; name = "Microsoft Flight Simulator 2024" },
  @{ appid = 367520; name = "Hollow Knight" },
  @{ appid = 105600; name = "Terraria" },
  @{ appid = 739630; name = "Phasmophobia" },
  @{ appid = 252490; name = "Rust" },
  @{ appid = 892970; name = "Valheim" },
  @{ appid = 620; name = "Portal" },
  @{ appid = 3405690; name = "FIFA 26" },
  @{ appid = 1364780; name = "Street Fighter 6" },
  @{ appid = 1778820; name = "TEKKEN 8" }
)

$summary = New-Object System.Collections.Generic.List[object]

Write-BatchLog "Batch start. total=$($games.Count) runDir=$runDir"
Write-State @{
  status = "running"
  started_at = (Get-Date).ToString("o")
  total = $games.Count
  completed = 0
  current = $null
  run_dir = $runDir
}

for ($index = 0; $index -lt $games.Count; $index++) {
  $game = $games[$index]
  $appid = [int]$game.appid
  $name = [string]$game.name
  $startedAt = Get-Date
  $safeName = ($name -replace '[\\/:*?"<>|]', '_')
  $stdoutPath = Join-Path $gameLogDir ("{0:D2}-{1}-{2}.stdout.log" -f ($index + 1), $appid, $safeName)
  $stderrPath = Join-Path $gameLogDir ("{0:D2}-{1}-{2}.stderr.log" -f ($index + 1), $appid, $safeName)

  Write-BatchLog ("START [{0}/{1}] appid={2} name={3}" -f ($index + 1), $games.Count, $appid, $name)
  Write-BatchLog ("LOGS  stdout={0}" -f $stdoutPath)
  Write-BatchLog ("LOGS  stderr={0}" -f $stderrPath)

  Write-State @{
    status = "running"
    started_at = (Get-Date).ToString("o")
    total = $games.Count
    completed = $index
    current = @{
      index = $index + 1
      appid = $appid
      name = $name
      started_at = $startedAt.ToString("o")
      stdout = $stdoutPath
      stderr = $stderrPath
    }
    run_dir = $runDir
  }

  $proc = Start-Process -FilePath python `
    -ArgumentList @(
      "$backendDir\scripts\run_offline_pipeline.py",
      "--appid", "$appid",
      "--review-pages", "all",
      "--use-llm-fallback",
      "--max-llm-reviews", "50"
    ) `
    -WorkingDirectory $repoRoot `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -PassThru

  $lastHeartbeatMinute = -1
  while (-not $proc.HasExited) {
    Start-Sleep -Seconds 5
    $elapsedSec = [int]((Get-Date) - $startedAt).TotalSeconds
    $elapsedMinute = [int]([math]::Floor($elapsedSec / 60))
    if ($elapsedMinute -gt $lastHeartbeatMinute) {
      $lastHeartbeatMinute = $elapsedMinute
      Write-BatchLog ("RUNNING [{0}/{1}] appid={2} elapsed={3}s pid={4}" -f ($index + 1), $games.Count, $appid, $elapsedSec, $proc.Id)
      Write-State @{
        status = "running"
        started_at = (Get-Date).ToString("o")
        total = $games.Count
        completed = $index
        current = @{
          index = $index + 1
          appid = $appid
          name = $name
          started_at = $startedAt.ToString("o")
          elapsed_seconds = $elapsedSec
          pid = $proc.Id
          stdout = $stdoutPath
          stderr = $stderrPath
        }
        run_dir = $runDir
      }
    }
  }

  $endedAt = Get-Date
  $durationSec = [int]($endedAt - $startedAt).TotalSeconds
  $exitCode = $proc.ExitCode

  $record = [pscustomobject][ordered]@{
    appid = $appid
    name = $name
    index = $index + 1
    started_at = $startedAt.ToString("o")
    ended_at = $endedAt.ToString("o")
    duration_seconds = $durationSec
    exit_code = $exitCode
    ok = ($exitCode -eq 0)
    stdout = $stdoutPath
    stderr = $stderrPath
  }
  $summary.Add($record)
  $summary | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $summaryPath

  if ($exitCode -eq 0) {
    Write-BatchLog ("OK   [{0}/{1}] appid={2} duration={3}s" -f ($index + 1), $games.Count, $appid, $durationSec)
  } else {
    Write-BatchLog ("FAIL [{0}/{1}] appid={2} duration={3}s exit={4}" -f ($index + 1), $games.Count, $appid, $durationSec, $exitCode)
    if (Test-Path $stderrPath) {
      $stderrTail = Get-Content $stderrPath -Tail 20 -ErrorAction SilentlyContinue
      foreach ($line in $stderrTail) {
        Write-BatchLog ("STDERR appid={0} {1}" -f $appid, $line)
      }
    }
  }
}

Write-State @{
  status = "finished"
  started_at = (Get-Date).ToString("o")
  total = $games.Count
  completed = $games.Count
  current = $null
  run_dir = $runDir
  summary = $summaryPath
}

Write-BatchLog "Batch finished. summary=$summaryPath"
