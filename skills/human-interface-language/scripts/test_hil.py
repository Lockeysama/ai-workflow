"""Behavioral checks; run with python3 scripts/test_hil.py."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import hil


class HilTests(unittest.TestCase):
    def test_preserves_distinct_layouts(self):
        examples = [
            '<section><h2>解释</h2><p>完整论述。</p></section>',
            '<section class="section-panel"><div class="section-head"><h2>比较</h2></div><div class="section-body"><table><tr><th>价格</th><th>条件</th></tr><tr><td>20 万</td><td>一年合同</td></tr></table></div></section>',
            '<article class="custom"><h2>研究记录</h2><p>证据不足。</p><details><summary>查看依据</summary><p>来源 A。</p></details></article>',
        ]
        for fragment in examples:
            output = hil.build(fragment, '标题')
            self.assertTrue(hil.inspect(output)[1]['ok'])
            self.assertEqual(hil.Parser(fragment).root.text().strip(),
                             hil.Parser(hil.build(fragment, '', toc='none')).root.text().replace('长文模式','').replace('Tab 模式','').replace('源码模式','').replace('复制当前内容','').replace('复制源码','').replace('用于检查当前 HIL 产物的 HTML、样式和交互结构。','').replace('展开全部细节','').replace('收起全部细节','').replace('打印 / 保存 PDF','').strip())

    def test_warnings_do_not_rewrite_or_fail(self):
        prose = '有必要保留的完整论证。' * 100
        output = hil.build('<h2>正文</h2><p>' + prose + '</p>', '研究')
        result = hil.inspect(output)[1]
        self.assertTrue(result['ok'])
        self.assertIn(prose, output)
        self.assertIn('long-paragraph', [x['code'] for x in result['warnings']])

    def test_nav_and_existing_ids(self):
        output = hil.build('<section id="existing" data-toc-label="短名"><h2>一</h2></section><h2>二</h2><p id="hil-section-2">已有 ID</p>', '标题')
        self.assertIn('href="#existing"', output)
        self.assertIn('</span>短名</a>', output)
        self.assertIn('id="hil-section-2-2"', output)
        self.assertTrue(hil.inspect(output)[1]['ok'])
        self.assertNotIn('<nav ', hil.build('<h2>一</h2><h2>二</h2>', '标题', toc='none'))

    def test_reading_warnings_preserve_content(self):
        detail = '需要保留的限定条件与证据。' * 12
        table = '<table id="options"><tr><th>方案</th><th>费用</th><th>限制</th><th>依据</th></tr><tr><td>A</td><td>未知</td><td>' + detail + '</td><td>' + detail + '</td></tr></table>'
        output = hil.build('<h1>重复标题</h1>' + table, '标题')
        report = hil.inspect(output)[1]
        self.assertTrue(report['ok'])
        codes = {w['code'] for w in report['warnings']}
        self.assertTrue({'multiple-h1', 'wide-table', 'dense-table'} <= codes)
        self.assertIn('options', next(w['message'] for w in report['warnings'] if w['code'] == 'dense-table'))
        self.assertEqual(output.count(detail), 2)
        self.assertIn('<h1>重复标题</h1>', output)
        wrapped = hil.build('<div class="table-scroll" tabindex="0">' + table + '</div>', '标题')
        codes = {w['code'] for w in hil.inspect(wrapped)[1]['warnings']}
        self.assertNotIn('wide-table', codes)
        self.assertNotIn('multiple-h1', codes)
        self.assertIn('dense-table', codes)

    def test_short_comparisons_and_prose_remain_supported(self):
        fragment = '<section><h2>比较</h2><table><tr><th>方案</th><th>条件</th></tr><tr><td>A</td><td>需预约</td></tr></table><p>连续论述仍可使用。</p></section>'
        result = hil.inspect(hil.build(fragment, '标题'))[1]
        self.assertTrue(result['ok'])
        self.assertFalse({'multiple-h1', 'wide-table', 'dense-table'} & {w['code'] for w in result['warnings']})

    def test_bundled_body_example(self):
        fragment = (Path(hil.__file__).resolve().parent.parent / 'assets/decision-body.html').read_text(encoding='utf-8')
        report = hil.inspect(hil.build(fragment, '方案选择示例'))[1]
        self.assertTrue(report['ok'])
        self.assertEqual(report['warnings'], [])

    def test_initial_navigation_and_chapters_do_not_require_scripts(self):
        # Check the generated document contract, not CSS spelling or pixel choices.
        # Alignment, fallback flow and print behavior need real browser checks.
        for count in (2, 3):
            with self.subTest(chapters=count):
                fragment = ''.join(
                    f'<section class="section-panel" id="chapter-{i}">'
                    f'<div class="section-head"><h2>章节 {i}</h2></div>'
                    f'<div class="section-body"><p>必要条件 {i}</p>'
                    f'<details><summary>依据 {i}</summary><p>完整证据 {i}</p>'
                    f'</details></div></section>' for i in range(count))
                parsed, report = hil.inspect(hil.build(fragment, '导航降级'))
                self.assertTrue(report['ok'], report['errors'])
                nodes = list(parsed.root.walk())
                toc = next(n for n in nodes if n.tag == 'nav' and n.has('toc'))
                self.assertEqual([n.attrs['href'] for n in toc.walk() if n.tag == 'a'],
                                 [f'#chapter-{i}' for i in range(count)])
                chapters = [n for n in nodes if n.has('section-panel')]
                self.assertEqual(len(chapters), count)
                self.assertEqual(sum(n.attrs.get('role') == 'tabpanel' for n in chapters),
                                 count if count >= 3 else 0)
                for node in [toc, *chapters]:
                    for ancestor in [node, *hil.ancestors(node)]:
                        self.assertNotIn('hidden', ancestor.attrs)
                        self.assertNotEqual(ancestor.attrs.get('aria-hidden'), 'true')
                for i, chapter in enumerate(chapters):
                    self.assertIn(f'必要条件 {i}', chapter.text())
                    self.assertIn(f'完整证据 {i}', chapter.text())

    def test_technical_example_preserves_semantics_in_tabs(self):
        fragment = (Path(hil.__file__).resolve().parent.parent / 'assets/technical-body.html').read_text(encoding='utf-8')
        source, source_report = hil.inspect(fragment, document=False)
        rendered, report = hil.inspect(hil.build(fragment, '技术说明示例'))
        self.assertTrue(source_report['ok'], source_report['errors'])
        self.assertTrue(report['ok'], report['errors'])
        source_nodes, output_nodes = list(source.root.walk()), list(rendered.root.walk())
        chapters = [n for n in source_nodes if n.has('section-panel')]
        panels = [n for n in output_nodes if n.attrs.get('role') == 'tabpanel']
        self.assertTrue(chapters)
        self.assertEqual([n.attrs['id'] for n in panels], [n.attrs['id'] for n in chapters])

        def chapter_id(node):
            return next(n.attrs.get('id') for n in hil.ancestors(node) if n.has('section-panel'))

        links = [n.attrs['href'] for n in source_nodes if n.tag == 'a' and n.attrs.get('href', '').startswith('#')]
        self.assertTrue(links)
        output_ids = {n.attrs['id'] for n in output_nodes if 'id' in n.attrs}
        output_links = {n.attrs.get('href') for n in output_nodes if n.tag == 'a'}
        for link in links:
            self.assertIn(link, output_links)
            self.assertIn(link[1:], output_ids)

        def steps(nodes):
            return [(n.attrs.get('id'), n.attrs.get('start'), n.attrs.get('reversed'),
                     [(c.attrs.get('value'), c.text().strip()) for c in n.children
                      if isinstance(c, hil.Node) and c.tag == 'li'])
                    for n in nodes if n.tag == 'ol' and n.has('step-list')]

        source_steps = steps(source_nodes)
        self.assertTrue(any(start and int(start) > 1 for _, start, _, _ in source_steps))
        self.assertEqual(steps(output_nodes), source_steps)
        for node in output_nodes:
            if node.has('rule-row'):
                self.assertEqual([c.tag for c in node.children if isinstance(c, hil.Node)], ['dt', 'dd'])

        def subsections(nodes):
            return [(n.attrs.get('id'), chapter_id(n),
                     [(c.tag, c.attrs.get('id')) for c in n.children
                      if isinstance(c, hil.Node) and c.tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6')])
                    for n in nodes if n.has('subsection')]

        def summaries(nodes):
            return [(chapter_id(n), [c.attrs['data-decision-role'] for c in n.walk()
                                    if 'data-decision-role' in c.attrs])
                    for n in nodes if n.has('decision-summary')]

        self.assertEqual(subsections(output_nodes), subsections(source_nodes))
        self.assertEqual(summaries(output_nodes), summaries(source_nodes))

        source_diagrams = [n for n in source_nodes if n.has('diagram')]
        output_diagrams = [n for n in output_nodes if n.has('diagram')]
        self.assertTrue(source_diagrams)
        self.assertEqual(len(output_diagrams), len(source_diagrams))
        for original, diagram in zip(source_diagrams, output_diagrams):
            self.assertEqual(chapter_id(diagram), chapter_id(original))
            for ancestor in hil.ancestors(diagram):
                if ancestor.has('section-panel'):
                    break
                self.assertNotEqual(ancestor.tag, 'details')
                self.assertNotIn('hidden', ancestor.attrs)
            caption = next(n for n in diagram.walk() if n.tag == 'figcaption')
            self.assertEqual(caption.text(), next(n.text() for n in original.walk() if n.tag == 'figcaption'))
            self.assertEqual(diagram.attrs.get('aria-labelledby'), caption.attrs.get('id'))
            status = next(n for n in diagram.walk() if n.has('diagram-status'))
            self.assertTrue(status.text().strip())
            self.assertNotIn('hidden', status.attrs)
            canvas = next(n for n in diagram.walk() if n.has('diagram-canvas'))
            self.assertEqual(canvas.attrs.get('role'), 'img')
            self.assertTrue(canvas.attrs.get('aria-label'))
            fallback = next(n for n in diagram.walk() if n.has('diagram-source'))
            self.assertEqual(fallback.tag, 'details')
            self.assertNotIn('hidden', fallback.attrs)
            code = next(n for n in fallback.walk() if n.tag == 'code')
            self.assertEqual(code.text(), next(n.text() for n in original.walk() if n.tag == 'code'))
            self.assertTrue(code.text().strip())

    def test_broken_structures_fail(self):
        for fragment, code in [
            ('<p id="x">A</p><p id="x">B</p>', 'duplicate-id'),
            ('<a href="#absent">跳转</a>', 'broken-anchor'),
            ('<details><p>缺少标题</p></details>', 'details-summary'),
            ('<figure class="diagram"><figcaption>流程</figcaption></figure>', 'diagram-part'),
            ('<section class="section-panel"><h2>不完整</h2></section>', 'panel-parts'),
        ]:
            result = hil.inspect(hil.build(fragment, '标题'))[1]
            self.assertFalse(result['ok'])
            self.assertIn(code, [x['code'] for x in result['errors']])

    def test_valid_diagram_scaffold(self):
        diagram = '<figure class="diagram"><figcaption>核对后交付。</figcaption><p class="diagram-status">待加载</p><div class="diagram-canvas" hidden></div><details class="diagram-source"><summary>源码</summary><pre><code>flowchart LR\nA --> B</code></pre></details></figure>'
        self.assertTrue(hil.inspect(hil.build(diagram, '图示'))[1]['ok'])

    def test_valid_tabs_scaffold(self):
        tabs = '''<section class="hil-tabs" data-hil-tabs aria-label="章节阅读">
          <div role="tablist"><button role="tab" id="tab-a" aria-controls="panel-a" aria-selected="true">A</button><button role="tab" id="tab-b" aria-controls="panel-b" aria-selected="false">B</button></div>
          <section id="panel-a" role="tabpanel" aria-labelledby="tab-a"><h2>第一章</h2>A 内容</section>
          <section id="panel-b" role="tabpanel" aria-labelledby="tab-b"><h2>第二章</h2>B 内容</section>
        </section>'''
        output = hil.build(tabs, '标题')
        self.assertIn('class="toc" data-hil-tab-toc', output)
        self.assertNotIn('data-hil-tab-toc hidden', output)
        self.assertIn('data-action="long-mode"', output)
        self.assertIn('data-action="tab-mode"', output)
        self.assertNotIn('data-action="source-mode"', output)
        self.assertIn('data-action="copy"', output)
        self.assertNotIn('data-action="copy-source"', output)
        self.assertIn('data-hil-tab-prev', output)
        self.assertIn('data-hil-tab-next', output)
        self.assertNotIn('data-hil-source-panel', output)
        self.assertTrue(hil.inspect(output)[1]['ok'])

    def test_auto_tabs_and_panel_normalization(self):
        content = ''.join(f'<section id="s{i}"><div class="section-head"><h2>章节 {i}</h2></div><div class="section-body"><p>内容</p></div></section>' for i in range(1, 4))
        output = hil.build(content, '标题')
        self.assertIn('data-hil-tabs', output)
        self.assertEqual(output.count('class="section-panel"'), 3)
        self.assertIn('role="tabpanel"', output)

    def test_invalid_tabs_scaffold(self):
        tabs = '<section class="hil-tabs" data-hil-tabs><div role="tablist"><button role="tab" id="tab-a" aria-controls="missing">A</button></div></section>'
        report = hil.inspect(hil.build(tabs, '标题'))[1]
        self.assertFalse(report['ok'])
        self.assertIn('tabs-structure', [x['code'] for x in report['errors']])

    def test_decision_summary_contract(self):
        summary = '''<section data-hil-decision>
          <div class="decision-summary" data-hil-decision-summary>
            <div data-decision-role="conclusion">结论</div>
            <div data-decision-role="evidence">依据</div>
            <div data-decision-role="boundary">边界</div>
            <div data-decision-role="next">下一步</div>
          </div>
        </section>'''
        self.assertTrue(hil.inspect(hil.build(summary, '标题'))[1]['ok'])
        incomplete = '<section data-hil-decision><div class="decision-summary"><div data-decision-role="conclusion">结论</div></div></section>'
        report = hil.inspect(hil.build(incomplete, '标题'))[1]
        self.assertFalse(report['ok'])
        self.assertIn('decision-summary-roles', [x['code'] for x in report['errors']])

    def test_escaping_and_literal_template_examples(self):
        output = hil.build('<p>&lt;script&gt; &amp; {{TITLE}}</p>', '<标题>')
        self.assertIn('<title>&lt;标题&gt;</title>', output)
        self.assertIn('<p>&lt;script&gt; &amp; {{TITLE}}</p>', output)
        self.assertTrue(hil.inspect(output)[1]['ok'])

    def test_english_controls(self):
        output = hil.build('<h2>First</h2><h2>Second</h2>', 'Study', lang='en')
        self.assertIn('lang="en"', output)
        self.assertIn('Hide contents', output)
        self.assertIn('Document contents', output)

    def test_explicit_closing_required(self):
        with self.assertRaises(ValueError):
            hil.build('<p>未闭合', '标题')

    def test_no_overwrite_on_invalid_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source, dest = Path(directory)/'body.html', Path(directory)/'report.html'
            source.write_text('<a href="#missing">坏链接</a>', encoding='utf-8')
            dest.write_text('原文不变', encoding='utf-8')
            result = subprocess.run([sys.executable, str(Path(hil.__file__)), 'render', '--content', str(source), '--output', str(dest), '--title', '验证'], capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(dest.read_text(encoding='utf-8'), '原文不变')
            source.write_text('<h2>论证</h2><p>' + '长论证。'*200 + '</p>', encoding='utf-8')
            result = subprocess.run([sys.executable, str(Path(hil.__file__)), 'render', '--content', str(source), '--output', str(dest), '--title', '验证'], capture_output=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn('长论证。'*200, dest.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
