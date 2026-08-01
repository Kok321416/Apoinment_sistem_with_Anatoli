# Cal.com–inspired theme (light + dark)

Цель: визуальный язык ближе к [cal.com](https://github.com/calcom/cal.com) - нейтрали, чёткий бренд-контраст, меньше glass/neon; **светлая и тёмная** тема на сайте, Mini App и Capacitor.

## Что берём у Cal.com (паттерны)

- Палитра: gray/neutral surfaces, brand = почти чёрный (light) / почти белый (dark)
- CTA: solid brand button, без фиолетово-бирюзовых градиентов
- Borders: тонкие нейтральные, не «glow»
- Booking UX уже частично: day-first, sticky steps (см. `MOBILE_UI_ADAPT.md`)
- Theme: `light` | `dark` | `system` (как `cssVarsPerTheme` / `theme: auto`)

## Что не копируем

- Их React/Tailwind код и шрифт Cal Sans как зависимость
- Чужой логотип/нейминг

## Архитектура у нас

| Слой | Файл |
|------|------|
| Токены | `app/static/css/tokens.css` - `[data-theme=dark|light]` |
| Anti-FOUC | inline script в `meta.html` до CSS |
| Toggle | `theme-toggle.js` + кнопка в header |
| Persist | `localStorage.ayc_theme` = `dark` \| `light` \| `system` |
| TG / Capacitor | тот же `data-theme` на `<html>`; StatusBar подстраивается |

Имена токенов (`--bg-900`, `--accent-primary`…) **сохраняем**, чтобы не переписывать все CSS сразу.

## Фазы

1. **Foundation (сейчас):** dual tokens + toggle + anti-FOUC + убрать worst purple hardcodes  
2. **Surfaces:** heroes/hubs/orbs без purple glow, плоские Cal-like cards  
3. **Booking polish:** ещё ближе к Booker (плотность, selected day circle)  
4. **Admin:** опционально позже (можно оставить dark-only)

## DoD фазы 1

- [x] Переключатель темы в шапке сайта и кабинета
- [x] Light/dark читаемы, без фиолетового «AI» акцента (токены + primary CTA)
- [x] Preference сохраняется; `system` следует OS
- [x] Mini App / Android видят ту же тему (`data-theme` на html)
- [x] `?v=` bumped на main.css / theme JS

## Как пользоваться

Кнопка «Системная / Светлая / Тёмная» в шапке - цикл по трём режимам.
Storage: `localStorage.ayc_theme`.
