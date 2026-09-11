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
                             hil.Parser(hil.build(fragment, '', toc='none')).root.text().replace('全部展开','').replace('全部收起','').replace('打印 / 保存 PDF','').strip())

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
