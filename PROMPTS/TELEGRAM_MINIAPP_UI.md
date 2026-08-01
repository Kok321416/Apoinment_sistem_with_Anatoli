# Telegram Mini App UI notes (Visual + Telegram)

## References used

- Official: https://core.telegram.org/bots/webapps (themeParams, safeAreaInset, contentSafeAreaInset)
- UI kit methodology: https://github.com/Telegram-Mini-Apps/TelegramUI
- Skills checklist: https://github.com/rithprohos/telegram-mini-app-skills

## Implementation

- Styles: `app/static/css/tg-webapp.css` (active when `.tg-webapp` on html/body)
- Bootstrap: `app/static/js/telegram-webapp.js` (viewport + safe-area CSS vars)
- Hub screens: `/tg/`, `/tg/apps/`
- All cabinet/booking pages inherit the same layer inside Telegram WebView

## DoD

- Touch targets ≥44px
- Single-column hubs on phone
- Safe areas respected (notch / TG chrome)
- Desktop browser outside Telegram unchanged
