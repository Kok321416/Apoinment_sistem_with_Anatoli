# Android app setup

## Locked choices

- App name: **Все клиенты здесь**
- Package: **`ru.allyourclients.app`**
- First test: **emulator** (virtual phone)

Для сборки нужны Android Studio, Android SDK и JDK 21 (`JAVA_HOME`).

## Create virtual phone (emulator) - do this in Android Studio

1. Open **Android Studio**.
2. **More Actions** → **Virtual Device Manager** (or Device Manager icon).
3. **Create Device** → phone (Pixel 6 / Pixel 7) → Next.
4. Download a system image: **API 34** or **API 35** (Recommended) → Finish.
5. Press **Play** on the device card - wait until home screen appears.

## Install the APK on the emulator

After the emulator is running, in PowerShell from the `mobile` folder:

```powershell
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
& "$env:ANDROID_HOME\platform-tools\adb.exe" devices
& "$env:ANDROID_HOME\platform-tools\adb.exe" install -r ".\android\app\build\outputs\apk\debug\app-debug.apk"
```

## Rebuild debug APK

```powershell
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
cd mobile\android
.\gradlew.bat assembleDebug
```

## RuStore release (AAB)

1. Keep the keystore file outside the repo. Do not commit it.
2. Copy `mobile/android/keystore.properties.example` → `keystore.properties`
   and put real `storePassword` / `keyPassword` (alias: `allyourclients`).
3. Build signed bundle:

```powershell
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
cd mobile\android
.\gradlew.bat bundleRelease
```

Output: `mobile\android\app\build\outputs\bundle\release\app-release.aab`

4. RuStore Console: https://console.rustore.ru/
   - register developer profile via VK ID
   - Apps → Add → «Все клиенты здесь»
   - package: `ru.allyourclients.app`
   - upload AAB (for AAB, upload signing certificate first per RuStore help)
