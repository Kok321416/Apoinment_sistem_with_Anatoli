# Android app setup (before RuStore)

## What we built

Capacitor shell: package `ru.allyourclients.app`, opens `https://allyourclients.ru` in WebView.
Same login (email / Telegram / VK / Yandex) and same MySQL as the website.

## What YOU need to install on this PC (required to build APK)

### 1. JDK 17 (not Java 8)

Download Temurin 17: https://adoptium.net/temurin/releases/?version=17  
Install, then in PowerShell check:

```powershell
java -version
```

Should show 17.x (not 1.8).

### 2. Android Studio

Download: https://developer.android.com/studio  
During setup install:
- Android SDK
- Android SDK Platform 35
- Android Virtual Device (optional emulator)

After install, open Android Studio once so SDK path is created, usually:
`C:\Users\Artem\AppData\Local\Android\Sdk`

### 3. Tell me when ready

Reply with:
1. `java -version` output
2. Does folder `C:\Users\Artem\AppData\Local\Android\Sdk` exist? (yes/no)
3. Phone for test: do you have an Android phone + USB cable? (yes/no)

Then I will run the debug APK build and give you the file to install.

## Build yourself (after Studio is installed)

```powershell
cd c:\Users\Artem\PycharmProjects\Apoinment_sistem_with_Anatoli\mobile
npm install
npx cap sync android
npx cap open android
```

In Android Studio: **Build → Build Bundle(s) / APK(s) → Build APK(s)**.
APK path roughly: `mobile\android\app\build\outputs\apk\debug\app-debug.apk`

Install on phone: enable «Установка из неизвестных источников» for this APK (test only; RuStore later).

## Questions for you (answer when you can)

1. App display name OK: «Все клиенты здесь»?
2. Package id OK: `ru.allyourclients.app`? (hard to change after RuStore publish)
3. Prefer first test on **emulator** or **real phone**?
4. Do you already have a RuStore developer account? (we use it later, not now)
