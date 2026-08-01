# Design System — Все клиенты здесь

Референсы: Linear, Notion, Stripe, Cal.com, Vercel. Стек: CSS tokens + Jinja components (не React `components/ui`).

## Принципы

1. Одна нейтральная гамма (light/dark)  
2. Sidebar + Workspace  
3. Touch ≥ 44px  
4. Motion 150–250ms, без прыжков  
5. Иконки монохром `currentColor`  

## Цвета (токены)

См. `app/static/css/tokens.css`. Продукт **только светлая тема**.

| Роль | Light |
|------|-------|
| Background | `#ffffff` / `#fafafa` |
| Surface / cards | `#fafafa` |
| Text primary | `#0a0a0a` |
| Text muted | `#737373` |
| Accent / primary CTA | `#111111` |
| On-accent | `#fafafa` |
| Border | `rgba(0,0,0,.1)` |
| Success / Warning / Danger | semantic greens/ambers/reds |

Интеграции: карточка в токенах сайта; бренд-цвет соцсети - только маленький badge, не весь UI.

## Типографика

- Display / H1 / H2: **Onest** (600–700), tighter tracking  
- H3 / body / UI: **Inter** (400–600)  
- Fluid clamp: Display XL → H1 → H2 → H3 с шагом ~1.25–1.35×  
- Токены: `--font-family-display`, `--font-family-base` в `tokens.css`  
- Короткие тексты; empty state: title + 1–2 строки + hint  

## Радиусы и тени

- xs 6 / sm 8 / md 12 (Linear-like)  
- shadow-xs/sm для cards; без glow  

## Компоненты (карта на файлы)

| UI | Где |
|----|-----|
| Buttons | `components.css` `.btn--*` |
| Cards | `.card`, hub cards |
| Inputs | `.input`, `.select` |
| Toast | `toast.js` + CSS |
| Cabinet layout | `layouts/app.html`, `cabinet_sidenav.html` |
| Empty | `.cabinet-empty` |
| Icons | `static/svg/icons/ui/*.svg` + CSS mask |

## Навигация

Desktop ≥900px: fixed sidenav  
Mobile: drawer + **bottom nav** (Главная / Записи|Календари / Клиенты|Услуги / Профиль)  

## Анимации

CSS only: `opacity`, `transform`; duration `--duration-fast/base`.  
Modal/drawer: fade + translateY/X. Без Framer Motion в этом стеке.  
Workspace: staggered `hub-workspace-in` (отключается в TG и при `prefers-reduced-motion`).  
Sheets: `.service-drawer` / `.client-drawer` / `.reschedule-overlay` - enter/exit 220ms.  

## Booking

Public: sticky steps (услуга → дата → время)  
Specialist calendar: day-first mobile; слоты одной гаммы accent  

## Ассеты бренда (из мудборда)

| Файл | Назначение |
|------|------------|
| `logo-mark-160.png` / `logo.svg` | mark: календарь + человек + галочка |
| `icons/ui/*.svg` | sidenav / bottom nav |
| Empty décor | CSS pattern + mark (без тяжёлых PNG) |

Логотип wordmark в UI: mark + `site_brand_name` текстом (как Cal.com).  
