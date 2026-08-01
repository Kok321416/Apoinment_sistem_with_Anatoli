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

## 1) Промпт: логотип (календарь + радостный человечек)

Скопируй целиком в Ideogram / Recraft / Leonardo / ImageFX / Designer.

```
Сделай логотип для SaaS онлайн-записи «Все клиенты здесь» (allyourclients.ru).

Главная идея знака (обязательно):
- календарь (лист календаря / рамка с сеткой дней / кольца-ушки сверху)
- и маленький человечек, который радостно прыгает (руки вверх или в прыжке, лёгкая динамика, улыбка без деталей лица)
- человечек связан с календарём: прыгает рядом, чуть поверх слота, или «выпрыгивает» из клетки дня
- ощущение: «запись прошла, клиент рад», тепло и простота

Стиль:
- минимализм как Cal.com + Linear + Notion
- плоская 2D геометрия, толщина линий ровная, как иконка приложения
- не детский мультфильм, не клипарт «stickman из PowerPoint», не фотореализм
- читается в favicon 16px и в PWA 512px

Цвета строго (light brand):
- фон белый #FFFFFF или прозрачный
- основной ink #0A0A0A
- можно один акцент серый #737373 для второстепенных линий
- без фиолетового, без неона, без радуги, без градиентов, без glow, без 3D, без стекла

Сделай 3 варианта mark:
A) календарь крупно + человечек прыгает справа/сверху от сетки
B) человечек внутри одной ячейки календаря (выбранный слот)
C) упрощённый силуэт: календарь-рамка + прыгающая фигурка из 3-5 простых форм

Плюс lockup:
- mark отдельно (квадрат 1:1)
- mark + wordmark «Все клиенты здесь» горизонтально
- шрифт геометрический, Inter-like, кириллица чёткая

Выдача:
1) мудборд 4 кадра
2) PNG на прозрачном фоне: 512 и 1024 (mark), горизонтальный lockup
3) вариант максимально упрощённый под SVG (мало деталей)

Ограничения:
- не добавляй телефоны, QR, флаги, логотипы Telegram/VK
- не пиши слоган, только название бренда в wordmark
- один сюжет, без коллажа и без мелкого шума
```

Короткий вариант (лимит символов):

```
Minimal flat logo for SaaS booking app "Все клиенты здесь": simple calendar icon + small happy stick-figure person joyfully jumping next to / out of a calendar day slot. Black #0A0A0A on white/transparent, Cal.com Linear style, 2D geometric, no purple, no neon, no 3D, no gradients. Square mark 1024 + horizontal lockup with clean Cyrillic wordmark.
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
