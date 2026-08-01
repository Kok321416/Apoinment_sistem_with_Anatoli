# Android shell (Capacitor → RuStore)

Loads live site `https://allyourclients.ru` in a WebView.

## Status

- Project generated: `mobile/android`
- Package: `ru.allyourclients.app`
- Plugins: App, StatusBar, SplashScreen
- **Next:** install JDK 17 + Android Studio on your PC, then build debug APK

See **SETUP_ANDROID.md** for your checklist.

## Commands

```bash
cd mobile
npm install
npx cap sync android
npx cap open android
```

## Branch

`track/android` → PR into `main` before prod deploy of bridge JS.
