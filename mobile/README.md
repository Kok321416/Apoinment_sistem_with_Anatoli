# Android shell (Capacitor → RuStore)

Loads the live site in a WebView so login, design, and MySQL stay the same as web.

## Status

Scaffold only. RuStore listing: **coming soon** (CTA on `/apps/`).

## Setup (local)

```bash
cd mobile
npm install
npx cap add android
npx cap sync android
npx cap open android
```

`capacitor.config.json` uses `server.url` = production site. Change for staging if needed.

## References

- https://github.com/ionic-team/capacitor
- RuStore publish / in-app updates docs

## Branch

Develop here on `track/android`. Merge to `main` via PR before store upload.
