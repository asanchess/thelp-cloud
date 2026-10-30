"""A single-sheet print edition; the full HTML report stays unchanged."""
from reporting import render_report


PRINT_STYLE='''
@media print {
 body { font-size:10pt;line-height:1.35; }
 .container {padding:0;max-width:none;}
 header.report-header {margin-bottom:14px;padding-bottom:12px;}
 .header-top {margin-bottom:10px;}
 .brand-mark,.date-badge {font-size:9pt;}
 .hero-title {font-size:20pt;line-height:1.15;margin-bottom:6px;}
 .hero-subtitle {font-size:10pt;line-height:1.35;}
 .meta-bar {font-size:8pt;margin-top:8px;gap:8px;}
 .stats-strip {grid-template-columns:repeat(3,1fr);gap:10px;margin:0;}
 .stat-card {padding:8px 10px;}
 .stat-label {font-size:8pt;letter-spacing:0;text-transform:none;}
 .stat-value {font-size:17pt;}
 section.report-section {margin-bottom:14px;}
 .section-header {margin-bottom:8px;padding-bottom:4px;}
 .section-title {font-size:13pt;}
 .lead-highlight {padding:10px 12px;margin-bottom:8px;}
 .lead-highlight .highlight-title,.highlight-title {font-size:11pt;margin-bottom:0;}
 .highlight-head {margin-bottom:4px;gap:4px;}
 .lead-highlight .highlight-summary,.highlight-summary {font-size:10pt;line-height:1.35;margin-bottom:0;}
 .highlights-list {gap:8px;}
 .highlight-card {padding:8px 12px;}
 .badge {font-size:7pt;padding:1px 4px;}
 .item-meta {font-size:8pt;gap:8px;margin-top:6px;}
 .evidence-links {font-size:7pt;margin-top:4px;}
 .actions-table {font-size:9pt;line-height:1.3;}
 .actions-table th,.actions-table td {padding:7px 8px;}
 .actions-table th {font-size:8pt;letter-spacing:0;text-transform:none;}
 .actions-table th:first-child,.actions-table td:first-child,
 .actions-table th:last-child,.actions-table td:last-child {display:none;}
 .actions-table th:nth-child(2) {width:58%!important;}
 .actions-table th:nth-child(3),.actions-table th:nth-child(4) {width:21%!important;}
 footer.report-footer {margin-top:12px;padding-top:8px;font-size:8pt;}
 .coverage-box {padding:8px 10px;}
 .coverage-title {font-size:8pt;}
}
'''


def render_brief(data):
    short=dict(data)
    short['highlights']=data['highlights'][:2]
    short['actions']=data['actions'][:3]
    short['sections']=[];short['chats']=[]
    used={key for item in short['highlights']+short['actions'] for key in item['evidence']}
    short['sources']=[s for s in data['sources'] if s['key'] in used]
    short['subtitle']='Два главных события и три ближайших действия. Полный разбор, все чаты и источники — в отдельном HTML-файле.'
    short['coverage']={'complete':data['coverage']['complete'],'limitation':'Краткая редакция. Все события, действия и ограничения — в полном HTML. Медиа не распознавались.'}
    return render_report(short).replace('</head>','<style>'+PRINT_STYLE+'</style></head>',1)
