"""The HTML of the e-mails of BornToShare: one layout (dark band, accent rule, title, blocks, buttons, footer), built
the way mail clients read it: tables, inline styles, no web font required (Inter / Space Grotesk when the client has
them, the system fonts otherwise), no script, no image. Every value is escaped here: callers pass plain text.
"""
from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Iterable

INK = "#0E1218"
MUTED = "#5B6470"
BODY = "#3F4A57"
LINE = "#E3E6E1"
SOFT = "#F4F6F2"
GROUND = "#ECEEE9"
ACCENT = "#B5F23B"
ACCENT_TEXT = "#3F6212"
ALERT = "#B42318"
SANS = "Inter, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
DISPLAY = "'Space Grotesk', Inter, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "'JetBrains Mono', Consolas, 'SFMono-Regular', Menlo, monospace"
MONTHS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre")
DAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


def e(value: object) -> str:
    return escape(str(value if value is not None else ""), quote=True)


def long_date(value: datetime | None) -> str:
    return f"{value.day} {MONTHS[value.month - 1]} {value.year}" if value else ""


def code(value: str) -> str:
    return f'<span style="font-family:{MONO};font-size:13px;color:{INK}">{e(value)}</span>'


def details(rows: Iterable[tuple[str, str]]) -> str:
    """Label / value rows in a framed table; values are HTML already (built with e() or code())."""
    rows = list(rows)
    cells = []
    for index, (label, value) in enumerate(rows):
        border = "" if index == len(rows) - 1 else "border-bottom:1px solid #EEF0EC;"
        cells.append(
            f'<tr><td style="{border}padding:14px 18px;width:120px;vertical-align:top;font:14px {SANS};color:{MUTED}">{e(label)}</td>'
            f'<td style="{border}padding:14px 18px;vertical-align:top;font:14px/1.5 {SANS};color:{INK}">{value}</td></tr>'
        )
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="border:1px solid {LINE};border-radius:14px;border-collapse:separate">{"".join(cells)}</table>')


def quote(label: str, text: str) -> str:
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {LINE};border-radius:14px;border-collapse:separate">'
            f'<tr><td style="padding:16px 18px;font:12px {SANS};color:{MUTED}">{e(label)}</td></tr>'
            f'<tr><td style="padding:0 18px 16px;font:italic 15px/1.55 {SANS};color:#26303B">« {e(text)} »</td></tr></table>')


def dark_box(eyebrow: str, path: str, note: str) -> str:
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{INK};border-radius:16px">'
            f'<tr><td style="padding:20px 22px 6px;font:600 12px {SANS};letter-spacing:0.1em;color:#C9D1DA">{e(eyebrow)}</td></tr>'
            f'<tr><td style="padding:0 22px 8px;font:16px {MONO};color:{ACCENT};overflow-wrap:anywhere">{e(path)}</td></tr>'
            f'<tr><td style="padding:0 22px 20px;font:13px/1.55 {SANS};color:#C9D1DA">{e(note)}</td></tr></table>')


def notice(eyebrow: str, line_html: str, note: str, *, tone: str = "alert") -> str:
    background, color = ("#FEF3F2", "#912018") if tone == "alert" else (SOFT, INK)
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{background};border-radius:16px">'
            f'<tr><td style="padding:18px 20px 4px;font:600 12px {SANS};letter-spacing:0.08em;color:{color}">{e(eyebrow)}</td></tr>'
            f'<tr><td style="padding:0 20px 4px;font:15px/1.55 {SANS};color:#26303B">{line_html}</td></tr>'
            f'<tr><td style="padding:0 20px 18px;font:13px/1.5 {SANS};color:{MUTED}">{e(note)}</td></tr></table>')


def file_list(items: Iterable[tuple[str, str]], more: int = 0) -> str:
    """(path, category label) rows with a chip; « and N more » under them."""
    items = list(items)
    rows = []
    for index, (path, label) in enumerate(items):
        border = "" if index == len(items) - 1 and not more else "border-bottom:1px solid #EEF0EC;"
        rows.append(
            f'<tr><td style="{border}padding:12px 18px;font:13px {MONO};color:#26303B;overflow-wrap:anywhere">{e(path)}</td>'
            f'<td align="right" style="{border}padding:12px 18px;white-space:nowrap">'
            f'<span style="font:600 12px {SANS};padding:3px 10px;border-radius:999px;background:#FEF3F2;color:#912018">{e(label)}</span></td></tr>'
        )
    if more:
        rows.append(f'<tr><td colspan="2" style="padding:12px 18px;font:13px {SANS};color:{MUTED}">et {more} autre(s)</td></tr>')
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="border:1px solid {LINE};border-radius:14px;border-collapse:separate">{"".join(rows)}</table>')


def date_block(day: datetime, title: str, path: str, progress: float | None, progress_label: str) -> str:
    bar = ""
    if progress is not None:
        width = max(2, min(100, int(progress * 100)))
        bar = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:12px">'
               f'<tr><td style="background:#EEF0EC;border-radius:999px;height:8px;line-height:8px;font-size:0">'
               f'<div style="width:{width}%;height:8px;background:{INK};border-radius:999px"></div></td></tr>'
               f'<tr><td style="padding-top:6px;font:12px {SANS};color:{MUTED}">{e(progress_label)}</td></tr></table>')
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {LINE};border-radius:18px;border-collapse:separate">'
            f'<tr><td width="150" align="center" style="background:{INK};border-radius:17px 0 0 17px;padding:24px 10px">'
            f'<div style="font:600 12px {SANS};letter-spacing:0.12em;color:{ACCENT}">{e(MONTHS[day.month - 1].upper())}</div>'
            f'<div style="font:700 58px/1 {DISPLAY};color:#FFFFFF;padding:4px 0">{day.day}</div>'
            f'<div style="font:13px {SANS};color:#C9D1DA">{e(DAYS[day.weekday()])} · {day.year}</div></td>'
            f'<td style="padding:20px 22px;vertical-align:middle">'
            f'<div style="font:600 15px {SANS};color:{INK}">{e(title)}</div>'
            f'<div style="font:12px {MONO};color:{MUTED};padding-top:3px;overflow-wrap:anywhere">{e(path)}</div>{bar}</td></tr></table>')


def button(label: str, url: str, *, primary: bool = True) -> str:
    style = (f"background:{INK};color:#FFFFFF;border:1px solid {INK}" if primary
             else f"background:#FFFFFF;color:{INK};border:1px solid #CDD2CB")
    return (f'<a href="{e(url)}" style="{style};display:inline-block;padding:15px 28px;border-radius:12px;'
            f'font:600 15px {SANS};text-decoration:none">{e(label)}</a>')


def layout(*, preheader: str, eyebrow: str, title: str, intro: str, blocks: Iterable[str] = (), buttons: Iterable[str] = (),
           footer: str, badge: str | None = None, alert: bool = False) -> str:
    """The whole e-mail. blocks and buttons are HTML from the helpers above; the rest is plain text."""
    rule = ALERT if alert else ACCENT
    eyebrow_color = ALERT if alert else ACCENT_TEXT
    badge_html = ""
    if badge:
        badge_style = (f"background:{ALERT};color:#FFFFFF;border:1px solid {ALERT}" if alert
                       else "color:#C9D1DA;border:1px solid #2A323D")
        badge_html = f'<span style="{badge_style};border-radius:999px;padding:5px 12px;font:600 12px {SANS}">{e(badge)}</span>'
    spaced = "".join(f'<tr><td style="padding:0 44px 22px">{block}</td></tr>' for block in blocks)
    actions = list(buttons)
    actions_html = ""
    if actions:
        cells = "".join(f'<td style="padding-right:10px">{item}</td>' for item in actions)
        actions_html = f'<tr><td style="padding:4px 44px 34px"><table role="presentation" cellpadding="0" cellspacing="0"><tr>{cells}</tr></table></td></tr>'
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><title>{e(title)}</title></head>
<body style="margin:0;padding:0;background:{GROUND}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{e(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{GROUND}"><tr><td align="center" style="padding:32px 12px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#FFFFFF;border-radius:20px;overflow:hidden">
<tr><td style="background:{INK};padding:24px 34px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td style="vertical-align:middle"><table role="presentation" cellpadding="0" cellspacing="0"><tr>
<td width="32" height="32" align="center" style="background:{ACCENT};border-radius:9px;font:700 15px {DISPLAY};color:{INK}">B</td>
<td style="padding-left:12px;font:700 19px {DISPLAY};color:#FFFFFF;letter-spacing:-0.01em">BornToShare</td></tr></table></td>
<td align="right" style="vertical-align:middle">{badge_html}</td></tr></table></td></tr>
<tr><td style="background:{rule};height:4px;line-height:4px;font-size:0">&nbsp;</td></tr>
<tr><td style="padding:38px 44px 10px;font:700 12px {SANS};letter-spacing:0.14em;color:{eyebrow_color}">{e(eyebrow.upper())}</td></tr>
<tr><td style="padding:0 44px 12px;font:600 28px/1.22 {DISPLAY};color:{INK};letter-spacing:-0.02em">{e(title)}</td></tr>
<tr><td style="padding:0 44px 26px;font:15px/1.6 {SANS};color:{BODY}">{e(intro)}</td></tr>
{spaced}{actions_html}
<tr><td style="padding:20px 44px 26px;border-top:1px solid #EEF0EC;font:12px/1.6 {SANS};color:{MUTED}">{e(footer)}<br>BornToShare · gouvernance des accès aux partages de fichiers</td></tr>
</table></td></tr></table></body></html>"""
