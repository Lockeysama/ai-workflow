#!/usr/bin/env python3
"""Build a HIL shell around flexible HTML, or check structural integrity. Stdlib only."""
import argparse
from collections import Counter
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import unquote

VOID = set('area base br col embed hr img input link meta param source track wbr'.split())


class Node:
    def __init__(self, tag='', attrs=(), parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children = []

    def has(self, name):
        return name in (self.attrs.get('class') or '').split()

    def walk(self):
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.walk()

    def text(self):
        if self.tag in ('script', 'style'):
            return ''
        return ''.join(child.text() if isinstance(child, Node) else child for child in self.children)

    def html(self):
        attrs = ''.join(' ' + k + ('' if v is None else '="' + escape(v, quote=True) + '"') for k, v in self.attrs.items())
        inner = ''.join(child.html() if isinstance(child, Node) else
                        child if self.tag in ('script', 'style') else escape(child, quote=False)
                        for child in self.children)
        if not self.tag:
            return inner
        return '<' + self.tag + attrs + '>' + ('' if self.tag in VOID else inner + '</' + self.tag + '>')


class Parser(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.problems = []
        self.feed(source)
        self.close()
        # The fragment contract uses explicit closing tags, not HTML optional endings.
        if len(self.stack) > 1:
            self.problems.append('未闭合标签：' + ', '.join(n.tag for n in self.stack[1:]))

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if len(self.stack) == 1 or self.stack[-1].tag != tag:
            self.problems.append('闭合标签顺序不匹配：' + tag)
            return
        self.stack.pop()

    def handle_data(self, data):
        self.stack[-1].children.append(data)

    def handle_comment(self, data):
        # Preserve comments, including custom diagram notes, when assembling fragments.
        node = Comment(data)
        self.stack[-1].children.append(node)


class Comment(Node):
    def __init__(self, data):
        super().__init__()
        self.data = data

    def text(self):
        return ''

    def html(self):
        return '<!--' + self.data + '-->'


def inspect(source, document=True):
    parsed = Parser(source)
    nodes = list(parsed.root.walk())
    errors = [{'code': 'html-balance', 'message': m} for m in parsed.problems]
    warnings = []

    def issue(bucket, code, message):
        bucket.append({'code': code, 'message': message})

    ids = Counter(n.attrs['id'] for n in nodes if n.attrs.get('id'))
    for value, count in ids.items():
        if count > 1:
            issue(errors, 'duplicate-id', 'ID 重复：' + value)
    for n in nodes:
        if 'id' in n.attrs and (not n.attrs['id'] or re.search(r'\s', n.attrs['id'])):
            issue(errors, 'invalid-id', 'ID 不能为空或含空白。')
        href = n.attrs.get('href') or ''
        if n.tag == 'a' and href.startswith('#') and len(href) > 1 and unquote(href[1:]) not in ids:
            issue(errors, 'broken-anchor', '本页锚点不存在：' + href)
        children = [c for c in n.children if isinstance(c, Node) and c.tag]
        if n.tag == 'details' and (not children or children[0].tag != 'summary' or not children[0].text().strip()):
            issue(errors, 'details-summary', 'details 的首个元素应为非空 summary。')
        if n.has('section-panel'):
            if not any(c.has('section-head') for c in children) or not any(c.has('section-body') for c in children):
                issue(errors, 'panel-parts', '已使用 section-panel，但缺少直接子元素 section-head / section-body。')
        if n.has('hil-tabs'):
            descendants = list(n.walk())
            tablist = next((c for c in descendants if c.attrs.get('role') == 'tablist'), None)
            tabs = [c for c in descendants if c.attrs.get('role') == 'tab']
            panels = [c for c in descendants if c.attrs.get('role') == 'tabpanel']
            if tablist is None or len(tabs) < 2 or len(tabs) != len(panels):
                issue(errors, 'tabs-structure', '章节 tab 需要 tablist、至少两个 tab，并为每个 tab 提供对应 tabpanel。')
            for tab in tabs:
                target = tab.attrs.get('aria-controls') or ''
                if target not in ids:
                    issue(errors, 'tabs-control-target', 'tab 的 aria-controls 不存在：' + target)
            for panel in panels:
                target = panel.attrs.get('aria-labelledby') or ''
                if target not in ids:
                    issue(errors, 'tabs-label-target', 'tabpanel 的 aria-labelledby 不存在：' + target)
        if 'data-hil-decision' in n.attrs:
            if not any(c.has('decision-summary') or 'data-hil-decision-summary' in c.attrs for c in n.walk()):
                issue(errors, 'decision-summary-missing', '标记为判断型章节的内容缺少 decision-summary。')
        if n.has('decision-summary') or 'data-hil-decision-summary' in n.attrs:
            descendants = list(n.walk())
            roles = {c.attrs.get('data-decision-role') for c in descendants}
            required = {'conclusion', 'evidence', 'boundary', 'next'}
            missing = sorted(required - roles)
            if missing:
                issue(errors, 'decision-summary-roles', '判断摘要缺少语义项：' + '、'.join(missing))
        if n.has('diagram'):
            descendants = list(n.walk())
            if not any(c.tag == 'figcaption' and c.text().strip() for c in descendants):
                issue(errors, 'diagram-description', 'Mermaid 图缺少常显的 figcaption 说明。')
            for cls in ('diagram-canvas', 'diagram-status', 'diagram-source'):
                if not any(c.has(cls) for c in descendants):
                    issue(errors, 'diagram-part', 'Mermaid 图缺少 ' + cls)
            if not any(c.tag == 'code' and c.text().strip() and any(a.has('diagram-source') for a in ancestors(c)) for c in descendants):
                issue(errors, 'diagram-source', 'Mermaid 图缺少可读取的源码。')
        if n.tag == 'p' and len(n.text().strip()) > 700:
            issue(warnings, 'long-paragraph', '有较长段落，请判断是否需要分组；完整论证可保持原样。')
        if (n.tag == 'section' or n.has('section-body')) and sum(c.tag == 'p' for c in children) >= 5:
            issue(warnings, 'dense-section', '章节有连续多段正文，请检查默认阅读量；无需为消除提示拆碎论述。')
        if n.tag == 'table' and not any(c.tag == 'th' for c in n.walk()):
            issue(warnings, 'table-headings', '表格缺少标题单元格，请判断是否需要补充比较维度。')
        if n.tag == 'table':
            table_nodes = list(n.walk())
            label = next((c.text().strip() for c in table_nodes if c.tag == 'caption'), '')
            label = label or n.attrs.get('id') or n.text().strip()[:48]
            rows = [c for c in table_nodes if c.tag == 'tr']
            columns = max((sum(isinstance(c, Node) and c.tag in ('td', 'th')
                               for c in row.children) for row in rows), default=0)
            if columns >= 4 and not any(a.has('table-scroll') for a in ancestors(n)):
                issue(warnings, 'wide-table', f'表格「{label}」有 {columns} 列且未使用 table-scroll；检查窄屏溢出，自定义滚动布局可保留。')
            long_cells = [c for c in table_nodes if c.tag == 'td' and len(c.text().strip()) > 100]
            if len(long_cells) >= 2:
                issue(warnings, 'dense-table', f'表格「{label}」有 {len(long_cells)} 个长文字单元格；检查是否应改成短比较表＋逐项说明。不要截断必要条件。')
    if document:
        if not any(n.tag == 'title' and n.text().strip() for n in nodes):
            issue(errors, 'document-title', '文档缺少非空 title。')
        if not any(n.tag == 'main' for n in nodes):
            issue(errors, 'document-main', '文档缺少 main 主体。')
        titles = [n.text().strip() for n in nodes if n.tag == 'h1']
        if len(titles) > 1:
            issue(warnings, 'multiple-h1', '文档出现多个 h1：' + ' / '.join(titles) + '。--title 已生成文档标题，请检查正文是否重复。')
        headings = [n for n in nodes if n.tag == 'h2']
        has_tabs = any(n.has('hil-tabs') for n in nodes)
        if headings and not any(n.has('section-panel') for n in nodes):
            issue(warnings, 'plain-sections', '未使用默认章节面板；自定义或论文式排版可以保留。')
        if len(headings) >= 3 and not any(n.has('toc') for n in nodes) and not has_tabs:
            issue(warnings, 'navigation', '多个主要章节没有目录，请判断导航价值。')
    return parsed, {'ok': not errors, 'errors': errors, 'warnings': warnings,
                    'scope': '仅检查结构与阅读提示，不证明事实、渲染、链接联网可达性或自动触发质量。'}


def ancestors(node):
    while node.parent:
        node = node.parent
        yield node


def unique_id(used, stem):
    value, i = stem, 2
    while value in used:
        value, i = stem + '-' + str(i), i + 1
    used.add(value)
    return value


def apply_reading_structure(parsed):
    """Normalize chapter panels and auto-enable tabs for independent flat chapters."""
    nodes = [n for n in parsed.root.children if isinstance(n, Node)]
    chapters = [n for n in nodes if n.tag == 'section' and any(c.has('section-head') for c in n.children if isinstance(c, Node))]
    for chapter in chapters:
        chapter.attrs['class'] = ' '.join(dict.fromkeys((chapter.attrs.get('class') or '').split() + ['section-panel']))
    explicit_tabs = any(n.has('hil-tabs') for n in parsed.root.walk())
    no_tabs = any('data-hil-no-tabs' in n.attrs for n in parsed.root.walk())
    if len(chapters) < 3 or explicit_tabs or len(chapters) != len(nodes):
        return
    recommended = 'long' if no_tabs else 'tab'
    tabs = Node('section', [('class', 'hil-tabs'), ('data-hil-tabs', ''), ('data-recommended-mode', recommended), ('aria-label', '章节阅读')], parsed.root)
    tablist = Node('div', [('class', 'hil-tablist'), ('role', 'tablist'), ('aria-label', '章节')], tabs)
    panels = Node('div', [('class', 'hil-tabpanels')], tabs)
    for i, chapter in enumerate(chapters, 1):
        heading = next((c for c in chapter.walk() if c.tag == 'h2'), None)
        label = heading.text().strip() if heading else f'第 {i} 章'
        tab_id, panel_id = f'hil-tab-{i}', chapter.attrs.get('id') or f'hil-panel-{i}'
        chapter.attrs['id'] = panel_id
        chapter.attrs['role'] = 'tabpanel'
        chapter.attrs['aria-labelledby'] = tab_id
        button = Node('button', [('type','button'), ('role','tab'), ('id',tab_id), ('aria-controls',panel_id), ('aria-selected','true' if i == 1 else 'false')], tablist)
        button.children.append(label)
        tablist.children.append(button)
        panels.children.append(chapter)
    tabs.children.extend([tablist, panels])
    parsed.root.children = [tabs]

def build(content, title, summary='', category='', meta='', footer='', toc='auto', extra_css='', lang='zh-CN'):
    parsed = Parser(content)
    if parsed.problems:
        raise ValueError('; '.join(parsed.problems))
    apply_reading_structure(parsed)
    nodes = list(parsed.root.walk())
    if any(n.tag in ('html', 'head', 'body', 'main') or n.has('toc') or n.has('toc-fab') for n in nodes):
        raise ValueError('输入应为正文片段，不含整页骨架或目录控件；这些由生成器提供。')
    used = {n.attrs['id'] for n in nodes if n.attrs.get('id')}
    entries = []
    for i, heading in enumerate(n for n in nodes if n.tag == 'h2'):
        # Prefer a stable section ID; free-form content can use heading IDs directly.
        target = next((n for n in ancestors(heading) if n.tag == 'section' and n.attrs.get('id')), heading)
        if not target.attrs.get('id'):
            target.attrs['id'] = unique_id(used, 'hil-section-' + str(i + 1))
        if not any(k == target.attrs['id'] for k, _ in entries):
            entries.append((target.attrs['id'], heading.attrs.get('data-toc-label') or target.attrs.get('data-toc-label') or heading.text().strip()))
    has_tabs = any(n.has('hil-tabs') for n in nodes)
    show_toc = toc == 'always' or (toc == 'auto' and len(entries) >= 2)
    if show_toc and not entries:
        raise ValueError('要求目录，但正文没有 h2；请提供实际章节或选择 --toc none。')
    nav = ''
    if show_toc:
        # Keep the TOC in the initial HTML: tab mode collapses it with a class once the script runs,
        # so a failed script still leaves navigation reachable.
        tab_toc_attrs = ' data-hil-tab-toc' if has_tabs else ''
        nav = '<nav class="toc"' + tab_toc_attrs + ' aria-label="文档目录"><strong>阅读目录</strong><ul>'
        for i, (key, label) in enumerate(entries, 1):
            nav += '<li><a href="#' + escape(key, quote=True) + '"><span aria-hidden="true">' + f'{i:02d}' + '</span>' + escape(label) + '</a></li>'
        nav += '</ul></nav>'
    template = (Path(__file__).resolve().parent.parent / 'assets/report.html').read_text(encoding='utf-8')
    template = template.replace('lang="zh-CN"', 'lang="' + escape(lang, quote=True) + '"')
    if lang.lower().startswith('en'):
        translations = {'收起目录':'Hide contents', '展开目录':'Show contents', '阅读操作':'Reading controls', '长文模式':'Long-form mode', 'Tab 模式':'Tab mode', '展开全部细节':'Expand details', '收起全部细节':'Collapse details', '图示暂时无法显示，请阅读图示说明；需要时可展开源码。':'Diagram unavailable. Read its description or expand the source.', '文档目录':'Document contents', '阅读目录':'Contents'}
        for original, translated in translations.items():
            template = template.replace(original, translated)
            nav = nav.replace(original, translated)
    if re.search(r'</style', extra_css, re.I):
        raise ValueError('extra CSS 不能包含 HTML 结束标签。')
    # One-pass replacement preserves literal {{TITLE}} examples inside user content.
    values = {k: escape(v) for k, v in dict(TITLE=title, SUMMARY=summary, CATEGORY=category, META=meta, FOOTER=footer).items()}
    values.update(CONTENT=parsed.root.html(), TOC=nav)
    for token, cls, tag in [('SUMMARY','lead','p'),('CATEGORY','eyebrow','p'),('META','meta','p'),('FOOTER',None,'footer')]:
        if not values[token]:
            template = template.replace(f'<{tag}' + (f' class="{cls}"' if cls else '') + '>{{' + token + '}}</' + tag + '>', '')
    if extra_css:
        template = template.replace('</head>', '<style>\n' + extra_css + '\n</style>\n</head>')
    return re.sub(r'\{\{(TITLE|SUMMARY|CATEGORY|META|FOOTER|CONTENT|TOC)\}\}', lambda m: values[m[1]], template)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    commands = ap.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check')
    check.add_argument('file', type=Path)
    render = commands.add_parser('render')
    render.add_argument('--content', type=Path, required=True)
    render.add_argument('--output', type=Path, required=True)
    render.add_argument('--title', required=True)
    for key in ('summary', 'category', 'meta', 'footer'):
        render.add_argument('--' + key, default='')
    render.add_argument('--lang', default='zh-CN')
    render.add_argument('--toc', choices=('auto', 'always', 'none'), default='auto')
    render.add_argument('--css', type=Path, help='Optional task-specific CSS; do not redefine fixed reading controls.')
    args = ap.parse_args()
    try:
        if args.command == 'check':
            _, report = inspect(args.file.read_text(encoding='utf-8'))
        else:
            if args.content.resolve() == args.output.resolve():
                raise ValueError('正文输入与整页输出不能使用同一个文件。')
            html = build(args.content.read_text(encoding='utf-8'), args.title, args.summary, args.category,
                         args.meta, args.footer, args.toc, args.css.read_text(encoding='utf-8') if args.css else '', args.lang)
            _, report = inspect(html)
            if report['ok']:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=args.output.parent, delete=False) as f:
                    tmp = Path(f.name)
                    f.write(html)
                try:
                    tmp.replace(args.output)
                finally:
                    tmp.unlink(missing_ok=True)
                report['output'] = str(args.output.resolve())
    except (ValueError, OSError) as e:
        report = {'ok': False, 'errors': [{'code': 'input', 'message': str(e)}], 'warnings': []}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
