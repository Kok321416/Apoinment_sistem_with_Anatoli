# Промпты для нейросети: логотип и фон dashboard

Сайт: allyourclients.ru  
Продукт: SaaS онлайн-записи «Все клиенты здесь»  
Стиль: Cal.com + Linear + Notion + Cursor empty workspace  
Тема: только light  

Цвета:
- фон #FFFFFF / #FAFAFA
- текст #0A0A0A
- акцент #111111
- muted #737373
- border #E5E5E5

Нельзя: purple neon, glassmorphism, 3D, фото людей, радуга, glow, градиенты бренда.

---

## 1) Промпт: логотип

Скопируй целиком в ChatGPT / Midjourney / Ideogram / Recraft / GPT Images.

```
Сделай логотип для SaaS онлайн-записи клиентов «Все клиенты здесь» (allyourclients.ru).

Задача бренда: спокойный продукт для специалистов (мастера, консультанты, врачи, коучи). Клиент записывается онлайн, специалист ведёт кабинет: календари, услуги, записи, клиенты.

Стиль: минимализм как Cal.com, Linear, Notion, GitHub. Геометрия, Inter-like шрифт, много воздуха. Не детский, не «салон красоты с розовым», не корпоративный клипарт.

Цвета строго:
- фон белый #FFFFFF или светло-серый #FAFAFA
- знак и текст почти чёрный #0A0A0A
- допускается один нейтральный серый #737373 для второстепенных линий
- без фиолетового, без неона, без радуги, без градиентов, без glow, без 3D, без теней-желе

Смысл знака (mark):
- тема записи / календаря / слота времени
- простой геометрический mark: рамка + сетка дней или точка «слот» + чистая геометрия
- читается в 16px (favicon) и в 512px (PWA)
- монохром, подходит под SVG currentColor

Сделай 3 варианта lockup:
A) только mark (квадрат 1:1)
B) mark + wordmark «Все клиенты здесь» горизонтально
C) только wordmark без иконки

Выдача:
1) мудборд 4 кадра на светлом фоне
2) финальные файлы:
   - logo-mark.png 512 и 1024 на прозрачном фоне
   - logo-horizontal.png 512 высоты (или эквивалент) на прозрачном фоне
   - logo-wordmark.png отдельно
3) кратко: почему выбран знак и как его упростить до SVG

Ограничения:
- не пиши длинный слоган в картинку, только название бренда
- не добавляй людей, телефоны, QR, флаги, Telegram/VK цвета
- не делай сложный орнамент: максимум 1 идея, 1 знак
```

Короткий вариант (если лимит символов у генератора):

```
Minimal monochrome logo for SaaS booking app "Все клиенты здесь". Calendar/slot geometric mark + clean Cyrillic wordmark. White background, ink #0A0A0A, Cal.com / Linear style. No purple, no neon, no 3D, no gradients, no people. Deliver square mark 1024 and horizontal lockup on transparent PNG.
```

---

## 2) Промпт: фон для /dashboard/ (empty workspace)

Страница: https://allyourclients.ru/dashboard/  
Сейчас: empty state кабинета (карточка по центру + декоративная сетка).  
Нужен спокойный фон/декор под карточку, не конкурирующий с текстом.

```
Сделай фоновую декорацию для empty state кабинета SaaS «Все клиенты здесь» на странице /dashboard/.

Контекст UI:
- светлый кабинет специалиста
- слева sidenav, справа большая рабочая зона
- по центру поверх фона будет белая карточка с логотипом, заголовком и кнопкой
- фон НЕ должен перебивать текст и кнопку
- референс атмосферы: Cursor empty workspace, Notion blank page, Linear soft canvas, Cal.com calm UI

Формат:
- PNG 2400x1600 (или 1600x1000)
- светлый фон #FAFAFA
- мягкая сетка / blueprint календаря / тонкие линии слотов
- очень низкий контраст: линии около #E5E5E5
- можно 1-2 тонких «рамки» по углам как пустой workspace
- оставь чистую центральную зону (примерно 40-50% по центру) почти без деталей под карточку UI

Стиль:
- flat 2D, без фото, без людей, без иконок соцсетей
- без фиолетового, без неона, без glassmorphism, без тяжёлых теней
- без крупного логотипа и без текста на картинке (текст добавим в HTML)
- ощущение «пустой аккуратный стол специалиста перед стартом работы»

Сделай 3 варианта:
1) calendar grid (мягкая сетка дней)
2) dotted workspace (точки + тонкие направляющие)
3) soft paper (почти пустой #FAFAFA с едва заметной текстурой бумаги и одной тонкой рамкой)

Выдача:
- превью каждого варианта
- финальный PNG без текста
- рекомендация: какой лучше под белую карточку по центру
```

Короткий вариант:

```
Light SaaS dashboard empty-state background, #FAFAFA, subtle calendar grid lines #E5E5E5, Cursor/Notion workspace style, soft blueprint, large empty center for a card overlay, no text, no logo, no people, no purple, no neon, flat 2D, 2400x1600 PNG.
```

---

## Куда потом вставить

| Ассет | Путь |
|-------|------|
| Mark / wordmark | `app/static/svg/logo.svg`, `logo-mark.svg`, `app/static/svg/brand/` |
| PNG пак | `app/static/img/brand/` |
| Фон dashboard | `app/static/svg/brand/cabinet-empty-decor.svg` или PNG в `app/static/img/brand/`, фон в `.cabinet-empty__art` (`app/static/css/app.css`) |

После генерации: скинь файлы в чат Cursor и напиши «подключи логотип и новый фон dashboard».
