# Mobile track — PWA + RuStore (no App Store)

## Strategy

- Android: Capacitor WebView → `https://allyourclients.ru` → publish **RuStore**.
- iPhone: **Telegram Mini App** + **PWA** (Safari → На экран «Домой»).
- One MySQL on Reg.ru; no separate mobile API.

## Git branches

| Branch | Owns |
|--------|------|
| `track/site` | Landing, `/apps/`, PWA manifest, web CSS |
| `track/telegram` | Bot `/apps`, Mini App hub cards |
| `track/android` | `mobile/` Capacitor + RuStore CI later |
| `main` | Production deploy |

Merge tracks → `main` via PR. Do not force-push `main`.

## Designer DoD for `/apps/`

- [ ] 375px: two platform blocks stack, CTAs thumb-friendly
- [ ] Tablet 768+: two columns optional, steps readable
- [ ] Copy uses hyphen `-`, no em dash
- [ ] Android shows «Скоро будет готово» until store link set
