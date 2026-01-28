# PowerShell скрипт для автоматического запуска Telegram бота на Windows
# Использование: .\deploy_bot.ps1

Write-Host "=== Настройка Telegram бота ===" -ForegroundColor Green

# Переходим в директорию проекта
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

# Проверяем наличие виртуального окружения
if (Test-Path "venv") {
    Write-Host "Активация виртуального окружения..." -ForegroundColor Yellow
    & .\venv\Scripts\Activate.ps1
}

# Устанавливаем зависимости
Write-Host "Установка зависимостей..." -ForegroundColor Yellow
pip install -r requirements.txt

# Применяем миграции
Write-Host "Применение миграций..." -ForegroundColor Yellow
python manage.py migrate

# Собираем статические файлы
Write-Host "Сбор статических файлов..." -ForegroundColor Yellow
python manage.py collectstatic --noinput

# Создаем задачу в планировщике Windows для автозапуска
Write-Host "Создание задачи в планировщике Windows..." -ForegroundColor Yellow

$taskName = "TelegramBotAppointmentSystem"
$pythonPath = Join-Path $scriptPath "venv\Scripts\python.exe"
$scriptPathFull = Join-Path $scriptPath "manage.py"
$workingDir = $scriptPath

# Удаляем существующую задачу, если есть
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Создаем новую задачу
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument "manage.py run_bot" -WorkingDirectory $workingDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Telegram Bot for Appointment System"

# Запускаем задачу
Start-ScheduledTask -TaskName $taskName

# Проверяем статус
Start-Sleep -Seconds 3
$taskInfo = Get-ScheduledTaskInfo -TaskName $taskName

if ($taskInfo.LastRunTime) {
    Write-Host "✓ Telegram бот успешно запущен!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Полезные команды:" -ForegroundColor Green
    Write-Host "  Проверить статус: Get-ScheduledTaskInfo -TaskName $taskName" -ForegroundColor Yellow
    Write-Host "  Остановить: Stop-ScheduledTask -TaskName $taskName" -ForegroundColor Yellow
    Write-Host "  Запустить: Start-ScheduledTask -TaskName $taskName" -ForegroundColor Yellow
    Write-Host "  Удалить: Unregister-ScheduledTask -TaskName $taskName" -ForegroundColor Yellow
} else {
    Write-Host "✗ Ошибка запуска бота. Проверьте настройки задачи." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=== Готово! ===" -ForegroundColor Green

