# Android app setup

## Locked choices

- App name: **Все клиенты здесь**
- Package: **`ru.allyourclients.app`**
- First test: **emulator** (virtual phone)

## Good news (this PC)

- Android Studio: `C:\Program Files\Android\Android Studio`
- SDK (hidden AppData): `C:\Users\Artem\AppData\Local\Android\Sdk`
- JDK for builds: Temurin **21** at `C:\Program Files\Eclipse Adoptium\jdk-21.0.12.8-hotspot`
- Debug APK built: `mobile\android\app\build\outputs\apk\debug\app-debug.apk`

`java -version` in PowerShell may still show 1.8 - that is OK for now. Builds must use JDK 21 via `JAVA_HOME`.

## Create virtual phone (emulator) - do this in Android Studio

1. Open **Android Studio**.
2. **More Actions** → **Virtual Device Manager** (or Device Manager icon).
3. **Create Device** → phone (Pixel 6 / Pixel 7) → Next.
4. Download a system image: **API 34** or **API 35** (Recommended) → Finish.
5. Press **Play** on the device card - wait until home screen appears.

## Install the APK on the emulator

After the emulator is running, in PowerShell:

```powershell
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
& "$env:ANDROID_HOME\platform-tools\adb.exe" devices
& "$env:ANDROID_HOME\platform-tools\adb.exe" install -r "C:\Users\Artem\PycharmProjects\Apoinment_sistem_with_Anatoli\mobile\android\app\build\outputs\apk\debug\app-debug.apk"
```

Or tell me «эмулятор запущен» - I will install the APK from here.

## Rebuild debug APK

```powershell
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-21.0.12.8-hotspot"
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
cd C:\Users\Artem\PycharmProjects\Apoinment_sistem_with_Anatoli\mobile\android
.\gradlew.bat assembleDebug
```

## RuStore release (AAB)

1. Keystore file (do not commit):
   `C:\Users\Artem\Documents\allclients\allyourclients-release.jks`
2. Copy `mobile/android/keystore.properties.example` → `keystore.properties`
   and put real `storePassword` / `keyPassword` (alias: `allyourclients`).
3. Build signed bundle:

```powershell
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-21.0.12.8-hotspot"
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
cd C:\Users\Artem\PycharmProjects\Apoinment_sistem_with_Anatoli\mobile\android
.\gradlew.bat bundleRelease
```

Output: `mobile\android\app\build\outputs\bundle\release\app-release.aab`

4. RuStore Console (browser): https://console.rustore.ru/
   - register developer profile via VK ID
   - Apps → Add → «Все клиенты здесь»
   - package: `ru.allyourclients.app`
   - upload AAB (for AAB, upload signing certificate first per RuStore help)
