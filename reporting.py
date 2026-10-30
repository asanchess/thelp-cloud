#!/usr/bin/env python3
"""
Reusable daily report renderer for THelp.
Standard library only; zero network/CDN dependencies; strict validation and HTML escaping.
"""

import html
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

_TELEGRAM_LINK_RE = re.compile(r"^https://t\.me/c/(\d+)/(\d+)$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_RU_MONTHS = [
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
]

_PRIORITY_TRANSLATION = {
    "high": "Высокий",
    "medium": "Средний",
    "low": "Низкий",
}

_PRIORITY_CLASSES = {
    "high": "badge-high",
    "medium": "badge-medium",
    "low": "badge-low",
}


def _escape(val: Any) -> str:
    """Strictly escape untrusted text and HTML attributes."""
    if val is None:
        return ""
    return html.escape(str(val), quote=True)


def _format_date_ru(iso_date: str) -> str:
    """Format YYYY-MM-DD date strictly without timezone manipulation."""
    try:
        dt = datetime.strptime(iso_date, "%Y-%m-%d")
        month_str = _RU_MONTHS[dt.month]
        return f"{dt.day} {month_str} {dt.year} г."
    except Exception as exc:
        raise ValueError(f"Invalid ISO date '{iso_date}': {exc}") from exc


def _validate_report_data(data: dict) -> None:
    """Validate data contract according to REPORTING_TASK.md."""
    if not isinstance(data, dict):
        raise ValueError("Input data must be a dictionary")

    # Date
    date_str = data.get("date")
    if not isinstance(date_str, str) or not _ISO_DATE_RE.match(date_str):
        raise ValueError("Field 'date' must be an ISO format string YYYY-MM-DD")
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"Invalid calendar date '{date_str}'") from exc

    # Title
    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Field 'title' is required and must be a non-empty string")

    # Sources & Source Keys
    sources = data.get("sources")
    if not isinstance(sources, list):
        raise ValueError("Field 'sources' must be a list")

    source_keys = set()
    for idx, s in enumerate(sources):
        if not isinstance(s, dict):
            raise ValueError(f"Source at index {idx} must be a dictionary")
        key = s.get("key")
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"Source at index {idx} must have a non-empty 'key'")
        if key in source_keys:
            raise ValueError(f"Duplicate source key: '{key}'")
        source_keys.add(key)

    # Highlights evidence check
    highlights = data.get("highlights", [])
    if not isinstance(highlights, list):
        raise ValueError("Field 'highlights' must be a list")
    for idx, h in enumerate(highlights):
        if not isinstance(h, dict):
            raise ValueError(f"Highlight at index {idx} must be a dictionary")
        for ev in h.get("evidence", []):
            if ev not in source_keys:
                raise ValueError(f"Highlight '{h.get('title')}' cites unknown source key '{ev}'")

    # Actions evidence check
    actions = data.get("actions", [])
    if not isinstance(actions, list):
        raise ValueError("Field 'actions' must be a list")
    for idx, a in enumerate(actions):
        if not isinstance(a, dict):
            raise ValueError(f"Action at index {idx} must be a dictionary")
        for ev in a.get("evidence", []):
            if ev not in source_keys:
                raise ValueError(f"Action '{a.get('text')}' cites unknown source key '{ev}'")

    # Chats check
    chats = data.get("chats", [])
    if not isinstance(chats, list):
        raise ValueError("Field 'chats' must be a list")
    for idx, c in enumerate(chats):
        if not isinstance(c, dict):
            raise ValueError(f"Chat at index {idx} must be a dictionary")
        count = c.get("count", 0)
        if not isinstance(count, int) or count < 0:
            raise ValueError(f"Chat count at index {idx} must be a non-negative integer")


def _render_stats(stats: List[Dict[str, Any]]) -> str:
    if not stats:
        return ""
    items_html = []
    for s in stats:
        lbl = _escape(s.get("label", ""))
        val = _escape(s.get("value", ""))
        items_html.append(
            f'<div class="stat-card">'
            f'<div class="stat-label">{lbl}</div>'
            f'<div class="stat-value">{val}</div>'
            f"</div>"
        )
    return (
        '<section class="report-section" aria-label="Ключевые показатели">'
        '<div class="stats-strip">' + "".join(items_html) + "</div>"
        "</section>"
    )


def _render_evidence_links(evidence: List[str]) -> str:
    if not evidence:
        return ""
    links = []
    for ev in evidence:
        e_esc = _escape(ev)
        links.append(f'<a href="#source-{e_esc}" class="evidence-ref-link" title="Источник {e_esc}">[{e_esc}]</a>')
    return '<div class="evidence-links">Источники: ' + " ".join(links) + "</div>"


def _render_highlights(highlights: List[Dict[str, Any]]) -> str:
    if not highlights:
        return ""

    out = ['<section class="report-section" aria-label="Главные события">']
    out.append('<div class="section-header"><h2 class="section-title">Главное за день</h2></div>')

    # Lead highlight
    lead = highlights[0]
    lead_title = _escape(lead.get("title", ""))
    lead_summary = _escape(lead.get("summary", ""))
    lead_cat = _escape(lead.get("category", ""))
    lead_when = _escape(lead.get("when", ""))
    lead_where = _escape(lead.get("where", ""))
    lead_urgency = lead.get("urgency", "low")
    lead_ev = _render_evidence_links(lead.get("evidence", []))

    urgency_badge = ""
    if lead_urgency in _PRIORITY_TRANSLATION:
        badge_cls = _PRIORITY_CLASSES.get(lead_urgency, "badge-neutral")
        badge_text = _PRIORITY_TRANSLATION[lead_urgency]
        urgency_badge = f'<span class="badge {badge_cls}">{badge_text}</span>'

    category_badge = f'<span class="badge badge-neutral">{lead_cat}</span>' if lead_cat else ""

    out.append('<div class="lead-highlight">')
    out.append('<div class="highlight-head">')
    out.append(f'<h3 class="highlight-title">{lead_title}</h3>')
    out.append(f"<div>{urgency_badge} {category_badge}</div>")
    out.append("</div>")
    out.append(f'<p class="highlight-summary">{lead_summary}</p>')
    out.append('<div class="item-meta">')
    if lead_where:
        out.append(f'<span class="item-meta-item">Где: <strong>{lead_where}</strong></span>')
    if lead_when:
        out.append(f'<span class="item-meta-item">Когда: <strong>{lead_when}</strong></span>')
    out.append("</div>")
    out.append(lead_ev)
    out.append("</div>")

    # Remaining highlights
    if len(highlights) > 1:
        out.append('<ul class="highlights-list">')
        for h in highlights[1:]:
            h_title = _escape(h.get("title", ""))
            h_summary = _escape(h.get("summary", ""))
            h_cat = _escape(h.get("category", ""))
            h_when = _escape(h.get("when", ""))
            h_where = _escape(h.get("where", ""))
            h_urgency = h.get("urgency", "low")
            h_ev = _render_evidence_links(h.get("evidence", []))

            u_badge = ""
            if h_urgency in _PRIORITY_TRANSLATION:
                b_cls = _PRIORITY_CLASSES.get(h_urgency, "badge-neutral")
                b_text = _PRIORITY_TRANSLATION[h_urgency]
                u_badge = f'<span class="badge {b_cls}">{b_text}</span>'
            c_badge = f'<span class="badge badge-neutral">{h_cat}</span>' if h_cat else ""

            card_urgency_cls = f"urgency-{h_urgency}" if h_urgency in ("high", "medium", "low") else "urgency-low"

            out.append(f'<li class="highlight-card {card_urgency_cls}">')
            out.append('<div class="highlight-head">')
            out.append(f'<h4 class="highlight-title">{h_title}</h4>')
            out.append(f"<div>{u_badge} {c_badge}</div>")
            out.append("</div>")
            out.append(f'<p class="highlight-summary">{h_summary}</p>')
            out.append('<div class="item-meta">')
            if h_where:
                out.append(f'<span class="item-meta-item">Где: <strong>{h_where}</strong></span>')
            if h_when:
                out.append(f'<span class="item-meta-item">Когда: <strong>{h_when}</strong></span>')
            out.append("</div>")
            out.append(h_ev)
            out.append("</li>")
        out.append("</ul>")

    out.append("</section>")
    return "\n".join(out)


def _render_actions(actions: List[Dict[str, Any]]) -> str:
    if not actions:
        return ""

    out = ['<section class="report-section" aria-label="Необходимые действия">']
    out.append('<div class="section-header"><h2 class="section-title">Требуемые действия</h2></div>')
    out.append('<div class="table-container">')
    out.append('<table class="actions-table">')
    out.append("<thead><tr>")
    out.append('<th scope="col" style="width: 14%;">Приоритет</th>')
    out.append('<th scope="col" style="width: 44%;">Действие</th>')
    out.append('<th scope="col" style="width: 18%;">Где</th>')
    out.append('<th scope="col" style="width: 14%;">Когда</th>')
    out.append('<th scope="col" style="width: 10%;">Статус</th>')
    out.append("</tr></thead><tbody>")

    for a in actions:
        text = _escape(a.get("text", ""))
        where = _escape(a.get("where", "—"))
        when = _escape(a.get("when", "—"))
        state = _escape(a.get("state", "—"))
        priority = a.get("priority", "medium")
        p_text = _PRIORITY_TRANSLATION.get(priority, _escape(str(priority)))
        p_cls = _PRIORITY_CLASSES.get(priority, "badge-neutral")
        ev_html = _render_evidence_links(a.get("evidence", []))

        out.append("<tr>")
        out.append(f'<td><span class="priority-pill {p_cls}">{p_text}</span></td>')
        out.append(f"<td><strong>{text}</strong>{ev_html}</td>")
        out.append(f"<td>{where}</td>")
        out.append(f"<td>{when}</td>")
        out.append(f"<td>{state}</td>")
        out.append("</tr>")

    out.append("</tbody></table></div></section>")
    return "\n".join(out)


def _render_sections(sections: List[Dict[str, Any]]) -> str:
    if not sections:
        return ""
    out = ['<section class="report-section" aria-label="Тематические разделы">']
    out.append('<div class="section-header"><h2 class="section-title">Разделы отчёта</h2></div>')

    for s in sections:
        title = _escape(s.get("title", ""))
        body = s.get("body", "")
        # Body is plain text with paragraphs; never Markdown/HTML
        paras = [p.strip() for p in body.split("\n\n") if p.strip()]
        body_html = "".join(f"<p>{_escape(p)}</p>" for p in paras) if paras else "<p></p>"

        out.append('<div class="editorial-section">')
        out.append(f"<h3>{title}</h3>")
        out.append(body_html)
        out.append("</div>")

    out.append("</section>")
    return "\n".join(out)


def _render_chats(chats: List[Dict[str, Any]]) -> str:
    if not chats:
        return ""
    out = ['<section class="report-section" aria-label="Обзор чатов">']
    out.append('<div class="section-header"><h2 class="section-title">Активность в чатах</h2></div>')
    out.append('<div class="chats-grid">')

    for c in chats:
        title = _escape(c.get("title", ""))
        count = c.get("count", 0)
        summary = _escape(c.get("summary", ""))

        out.append('<div class="chat-card">')
        out.append('<div class="chat-card-header">')
        out.append(f'<span class="chat-card-title">{title}</span>')
        out.append(f'<span class="chat-card-count">{count} сообщ.</span>')
        out.append("</div>")
        out.append(f'<div class="chat-card-summary">{summary}</div>')
        out.append("</div>")

    out.append("</div></section>")
    return "\n".join(out)


def _render_sources(sources: List[Dict[str, Any]]) -> str:
    if not sources:
        return ""
    out = ['<section class="report-section" aria-label="Первоисточники">']
    out.append('<div class="section-header"><h2 class="section-title">Первоисточники и цитаты</h2></div>')

    for s in sources:
        key = _escape(s.get("key", ""))
        title = _escape(s.get("title", ""))
        time_str = _escape(s.get("time", ""))
        quote = _escape(s.get("quote", ""))
        chat_id = _escape(s.get("chat_id", ""))
        message_id = _escape(s.get("message_id", ""))
        raw_url = s.get("url")

        url_html = ""
        if isinstance(raw_url, str) and _TELEGRAM_LINK_RE.match(raw_url.strip()):
            safe_url = _escape(raw_url.strip())
            url_html = f'<div class="source-link">Ссылка: <a href="{safe_url}" rel="noopener noreferrer">{safe_url}</a></div>'
        elif raw_url:
            url_html = f'<div class="source-link">Ссылка: {_escape(str(raw_url))}</div>'

        meta_parts = []
        if chat_id:
            meta_parts.append(f'Чат ID: <code>{chat_id}</code>')
        if message_id:
            meta_parts.append(f'Сообщение ID: <code>{message_id}</code>')
        meta_html = f'<div class="source-meta">{" · ".join(meta_parts)}</div>' if meta_parts else ""

        out.append(f'<details class="source-details" id="source-{key}">')
        out.append(f'<summary class="source-summary"><span>[{key}] {title}</span><span>{time_str}</span></summary>')
        out.append('<div class="source-content">')
        if meta_html:
            out.append(meta_html)
        if quote:
            out.append(f'<div class="source-quote">{quote}</div>')
        if url_html:
            out.append(url_html)
        out.append("</div>")
        out.append("</details>")

    out.append("</section>")
    return "\n".join(out)


def render_report(data: dict) -> str:
    """
    Pure renderer function taking structured report dictionary and returning complete HTML document.
    Template lives alongside reporting.py; input cannot select template paths.
    Uses single-pass regex replacement to preserve literal placeholders in user data.
    """
    _validate_report_data(data)

    template_path = Path(__file__).resolve().parent / "report_template.html"
    if not template_path.is_file():
        raise FileNotFoundError(f"Template not found at {template_path}")

    template_content = template_path.read_text(encoding="utf-8")

    # Header fields
    iso_date = data.get("date", "")
    date_formatted = _format_date_ru(iso_date)
    title = _escape(data.get("title", ""))
    page_title = f"{title} — {date_formatted}"

    subtitle_val = data.get("subtitle", "")
    subtitle_block = f'<p class="hero-subtitle">{_escape(subtitle_val)}</p>' if subtitle_val else ""

    period_label = _escape(data.get("period_label", ""))
    generated_at = _escape(data.get("generated_at", ""))

    # Sections
    stats_block = _render_stats(data.get("stats", []))
    highlights_block = _render_highlights(data.get("highlights", []))
    actions_block = _render_actions(data.get("actions", []))
    sections_block = _render_sections(data.get("sections", []))
    chats_block = _render_chats(data.get("chats", []))
    sources_block = _render_sources(data.get("sources", []))

    # Coverage
    coverage = data.get("coverage", {})
    coverage_complete = coverage.get("complete", True)
    cov_status = "Полное" if coverage_complete else "Ограниченное"
    cov_limitation = _escape(coverage.get("limitation", "Ограничений нет."))

    meta_description = _escape(f"Личный выпуск THelp от {date_formatted}: {title}")

    replacements = {
        "__PAGE_TITLE__": page_title,
        "__META_DESCRIPTION__": meta_description,
        "__DATE_FORMATTED__": date_formatted,
        "__TITLE__": title,
        "__SUBTITLE_BLOCK__": subtitle_block,
        "__PERIOD_LABEL__": period_label,
        "__GENERATED_AT__": generated_at,
        "__STATS_BLOCK__": stats_block,
        "__HIGHLIGHTS_BLOCK__": highlights_block,
        "__ACTIONS_BLOCK__": actions_block,
        "__SECTIONS_BLOCK__": sections_block,
        "__CHATS_BLOCK__": chats_block,
        "__SOURCES_BLOCK__": sources_block,
        "__COVERAGE_STATUS__": cov_status,
        "__COVERAGE_LIMITATION__": cov_limitation,
    }

    pattern = re.compile("|".join(re.escape(k) for k in replacements.keys()))
    html_out = pattern.sub(lambda m: replacements[m.group(0)], template_content)

    return html_out


def write_report(data: dict, destination: Path) -> Path:
    """
    Renders report and atomically writes UTF-8 output to destination.
    Uses tempfile in the same directory and replaces atomically.
    """
    dest_path = Path(destination).resolve()
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    rendered_html = render_report(data)

    tmp_path = dest_path.with_name(f".{dest_path.name}.tmp.{os.getpid()}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(rendered_html)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, dest_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

    return dest_path


def main() -> None:
    """CLI handler: python reporting.py input.json output.html"""
    if len(sys.argv) < 3:
        print("Usage: python reporting.py <input.json> <output.html>", file=sys.stderr)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not input_path.is_file():
        print(f"Error: input file '{input_path}' not found", file=sys.stderr)
        sys.exit(1)

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        write_report(data, output_path)
    except Exception as exc:
        print(f"Error generating report: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
