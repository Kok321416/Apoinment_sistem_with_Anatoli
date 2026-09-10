"""Excel (.xlsx) exporters for specialist statistics and client diagnostics."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


_HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
_HEADER_FONT = Font(color="FFFFFF", bold=True, name="Calibri", size=11)
_TITLE_FONT = Font(bold=True, name="Calibri", size=14, color="1F4E79")
_LABEL_FONT = Font(bold=True, name="Calibri", size=11)
_THIN = Border(
    left=Side(style="thin", color="D0D7DE"),
    right=Side(style="thin", color="D0D7DE"),
    top=Side(style="thin", color="D0D7DE"),
    bottom=Side(style="thin", color="D0D7DE"),
)
_ZEBRA = PatternFill("solid", fgColor="F5F8FC")
_SECTION_FILL = PatternFill("solid", fgColor="D6E3F0")


def _autosize(ws, min_width: int = 10, max_width: int = 42) -> None:
    for col_cells in ws.columns:
        letter = get_column_letter(col_cells[0].column)
        length = 0
        for cell in col_cells:
            val = "" if cell.value is None else str(cell.value)
            length = max(length, len(val))
        ws.column_dimensions[letter].width = max(min_width, min(max_width, length + 2))


def _style_header_row(ws, row: int, col_count: int) -> None:
    for col in range(1, col_count + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _THIN


def _style_body(ws, start_row: int, end_row: int, col_count: int) -> None:
    for r in range(start_row, end_row + 1):
        for c in range(1, col_count + 1):
            cell = ws.cell(row=r, column=c)
            cell.border = _THIN
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            if (r - start_row) % 2 == 1:
                cell.fill = _ZEBRA


def consultations_workbook(
    rows: list[dict[str, Any]],
    *,
    date_from: str,
    date_to: str,
    specialist_name: str = "",
) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Консультации"

    ws["A1"] = "Статистика консультаций"
    ws["A1"].font = _TITLE_FONT
    ws.merge_cells("A1:K1")
    ws["A2"] = f"Период: {date_from} — {date_to}"
    if specialist_name:
        ws["A3"] = f"Специалист: {specialist_name}"

    headers = [
        "Дата",
        "Время",
        "Статус",
        "Услуга",
        "Календарь",
        "Клиент",
        "Телефон",
        "Email",
        "Telegram",
        "Цена",
        "Заметки",
    ]
    header_row = 5
    for i, h in enumerate(headers, start=1):
        ws.cell(row=header_row, column=i, value=h)
    _style_header_row(ws, header_row, len(headers))
    ws.row_dimensions[header_row].height = 22

    for idx, row in enumerate(rows):
        r = header_row + 1 + idx
        values = [
            row.get("date") or "",
            row.get("time_range") or row.get("time") or "",
            row.get("status_label") or row.get("status") or "",
            row.get("service") or "",
            row.get("calendar") or "",
            row.get("client_name") or "",
            row.get("client_phone") or "",
            row.get("client_email") or "",
            row.get("client_telegram") or "",
            row.get("price") if row.get("price") is not None else "",
            row.get("notes") or "",
        ]
        for c, val in enumerate(values, start=1):
            ws.cell(row=r, column=c, value=val)

    if rows:
        _style_body(ws, header_row + 1, header_row + len(rows), len(headers))
    _autosize(ws)
    ws.freeze_panes = "A6"

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def client_diagnostics_workbook(
    *,
    profile: dict[str, Any],
    results: list[dict[str, Any]],
) -> bytes:
    wb = Workbook()

    # --- Profile sheet ---
    ws = wb.active
    ws.title = "Профиль"
    ws["A1"] = "Краткие данные клиента"
    ws["A1"].font = _TITLE_FONT
    ws.merge_cells("A1:B1")

    profile_rows = [
        ("Имя", profile.get("name") or ""),
        ("Телефон", profile.get("phone") or ""),
        ("Email", profile.get("email") or ""),
        ("Telegram", profile.get("telegram") or ""),
        ("Заметки", profile.get("notes") or ""),
        ("ID карточки", profile.get("id") or ""),
        ("Выгружено", datetime.now().strftime("%d.%m.%Y %H:%M")),
    ]
    ws["A3"] = "Поле"
    ws["B3"] = "Значение"
    _style_header_row(ws, 3, 2)
    for i, (label, value) in enumerate(profile_rows, start=4):
        ws.cell(row=i, column=1, value=label).font = _LABEL_FONT
        ws.cell(row=i, column=2, value=value)
        for c in (1, 2):
            ws.cell(row=i, column=c).border = _THIN
            if i % 2 == 0:
                ws.cell(row=i, column=c).fill = _ZEBRA
    _autosize(ws, min_width=14, max_width=60)

    # --- Summary sheet ---
    summary = wb.create_sheet("Диагностика — сводка")
    summary["A1"] = "Результаты диагностики"
    summary["A1"].font = _TITLE_FONT
    summary.merge_cells("A1:F1")

    sum_headers = ["Дата", "Тест", "Код", "Краткий итог", "Шкалы (сводка)", "ID"]
    for i, h in enumerate(sum_headers, start=1):
        summary.cell(row=3, column=i, value=h)
    _style_header_row(summary, 3, len(sum_headers))

    for idx, r in enumerate(results):
        row_i = 4 + idx
        scales = r.get("scales") or []
        scales_txt = "; ".join(
            f"{s.get('title') or s.get('code')}: {s.get('score')}"
            f"{(' (' + str(s.get('band_label')) + ')') if s.get('band_label') else ''}"
            for s in scales
        )
        completed = r.get("completed_at")
        if hasattr(completed, "strftime"):
            completed = completed.strftime("%d.%m.%Y %H:%M")
        values = [
            completed or "",
            r.get("title") or "",
            r.get("test_code") or "",
            r.get("summary") or "",
            scales_txt,
            r.get("id") or "",
        ]
        for c, val in enumerate(values, start=1):
            summary.cell(row=row_i, column=c, value=val)
    if results:
        _style_body(summary, 4, 3 + len(results), len(sum_headers))
    _autosize(summary, max_width=48)
    summary.freeze_panes = "A4"

    # --- Scales detail sheet ---
    scales_ws = wb.create_sheet("Шкалы")
    scales_ws["A1"] = "Шкалы по тестам"
    scales_ws["A1"].font = _TITLE_FONT
    scales_ws.merge_cells("A1:H1")
    scale_headers = [
        "Дата теста",
        "Тест",
        "Код теста",
        "Шкала",
        "Код шкалы",
        "Балл",
        "Диапазон",
        "Уровень / интерпретация",
    ]
    for i, h in enumerate(scale_headers, start=1):
        scales_ws.cell(row=3, column=i, value=h)
    _style_header_row(scales_ws, 3, len(scale_headers))

    row_i = 4
    for r in results:
        completed = r.get("completed_at")
        if hasattr(completed, "strftime"):
            completed = completed.strftime("%d.%m.%Y %H:%M")
        scales = r.get("scales") or []
        if not scales:
            values = [
                completed or "",
                r.get("title") or "",
                r.get("test_code") or "",
                "—",
                "",
                "",
                "",
                r.get("summary") or "",
            ]
            for c, val in enumerate(values, start=1):
                scales_ws.cell(row=row_i, column=c, value=val)
            row_i += 1
            continue
        for s in scales:
            band = s.get("band_label") or ""
            interp = s.get("interpretation") or ""
            level = s.get("band_level") or ""
            level_txt = " / ".join(x for x in (band, level, interp) if x)
            mn, mx = s.get("min"), s.get("max")
            rng = ""
            if mn is not None or mx is not None:
                rng = f"{mn if mn is not None else '—'}–{mx if mx is not None else '—'}"
            values = [
                completed or "",
                r.get("title") or "",
                r.get("test_code") or "",
                s.get("title") or "",
                s.get("code") or "",
                s.get("score") if s.get("score") is not None else "",
                rng,
                level_txt,
            ]
            for c, val in enumerate(values, start=1):
                cell = scales_ws.cell(row=row_i, column=c, value=val)
                cell.border = _THIN
                if row_i % 2 == 0:
                    cell.fill = _ZEBRA
            row_i += 1

    if row_i > 4:
        _style_body(scales_ws, 4, row_i - 1, len(scale_headers))
    # section tint on header already applied
    _ = _SECTION_FILL
    _autosize(scales_ws, max_width=40)
    scales_ws.freeze_panes = "A4"

    answers_ws = wb.create_sheet("Анамнез")
    answers_ws["A1"] = "Ответы опроса статуса"
    answers_ws["A1"].font = _TITLE_FONT
    answers_ws.merge_cells("A1:E1")
    ans_headers = ["Дата", "Вопрос", "Ответ", "Уточнение", "Код"]
    for i, h in enumerate(ans_headers, start=1):
        answers_ws.cell(row=3, column=i, value=h)
    _style_header_row(answers_ws, 3, len(ans_headers))
    ans_row = 4
    for r in results:
        completed = r.get("completed_at")
        if hasattr(completed, "strftime"):
            completed = completed.strftime("%d.%m.%Y %H:%M")
        interp = r.get("interpretation") or {}
        rows = interp.get("answers") or r.get("answer_rows") or []
        if not rows:
            continue
        for row in rows:
            values = [
                completed or "",
                row.get("question") or "",
                row.get("answer") or "",
                row.get("note") or "",
                row.get("id") or "",
            ]
            for c, val in enumerate(values, start=1):
                answers_ws.cell(row=ans_row, column=c, value=val)
            ans_row += 1
    if ans_row > 4:
        _style_body(answers_ws, 4, ans_row - 1, len(ans_headers))
    _autosize(answers_ws, max_width=48)
    answers_ws.freeze_panes = "A4"

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
