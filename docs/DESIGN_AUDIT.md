# Design Audit — Все клиенты здесь

Дата: 2026-08-01  
Стек: FastAPI + Jinja2 + CSS/JS (не React). Framer Motion / shadcn не подключаем как runtime - паттерны переносим в CSS + vanilla JS.

## Что уже хорошо

- Cabinet shell: Sidebar + Workspace (Linear/Notion-like)
- Light / dark токены (Cal.com neutrals)
- Day-first календарь на mobile, sticky steps в публичной записи
- Mini App shell (`tg-webapp`) с safe-area

## Проблемы UX

| Зона | Проблема |
|------|----------|
| Обзор | Empty state слишком «голый» - нет визуального якоря уровня Notion |
| Навигация | Иконки sidenav через `<img>` с фиксированным цветом / invert - плохо для light/dark |
| Mobile | Только hamburger drawer; нет bottom nav как у Linear/Cal mobile |
| Хабы | Heroes с декоративными glow (скрыты), карточки всё ещё «CRM-плотные» |
| Запись | Публичный booking лучше кабинета; specialist bookings ещё не Cal.com-уровень |
| Empty/loading | Мало skeleton; «пусто» без CTA |

## Проблемы UI

- Старый `logo.svg` с фиолетовым градиентом конфликтует с нейтральной системой
- Радужные слоты календаря уже нейтрализованы - держать
- Интеграции местами brand-color, нужна единая оболочка карточек
- Нет единой шкалы radius/shadow для «Linear cards»

## Проблемы адаптивности

- 320–390: workspace padding ок, bottom actions иногда пересекаются с footer
- TG Mini App: cabinet frame учтён, но denser list cells ещё не везде
- Capacitor = тот же CSS; bottom nav критичен для большого пальца

## План изменений (фазы)

### Фаза A (сейчас)
1. DESIGN_SYSTEM.md + audit  
2. Новый mark + набор stroke-иконок `currentColor` / mask  
3. Украшенный `.cabinet-empty`  
4. Mobile bottom navigation  
5. Подключение иконок в sidenav  

### Фаза B
- Унификация hub cards / filters / empty+skeleton  
- Booking list day/week/month polish  
- Integrations cards в одной оболочке  

### Фаза C
- Soft page transitions (CSS), sheet/drawer patterns  
- Browser QA 320–1440 + TG  

## Ограничения

- Не ломать API / bot / auth flows  
- Не force-push main  
- Админка desktop-only  
- «SPA без перезагрузки» на Jinja = полноценные URL; UX shell уже Sidebar+Workspace. Полный client-side router - отдельный эпик  
