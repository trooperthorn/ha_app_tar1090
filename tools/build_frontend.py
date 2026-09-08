"""Stage the local frontend. Upstream files stay recognizable for merges."""
import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
SCRIPTS = {'early.js','defaults.js','config.js','dbloader.js','registrations.js','formatter.js',
           'flags.js','layers.js','geomag2020.js','markers.js','planeObject.js','activityHistory.js','script.js'}


class LocalHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out, self.skip = [], []
    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if self.skip:
            if tag not in VOID: self.skip.append(tag)
            return
        identity = attributes.get('id', '')
        remove = (tag in ('noscript','footer') or
                  re.search(r'adsbexchange_|freestar|tracking_leaderboard|ax-identity|leaderboard|premium_text|pmLink|full_details', identity) or
                  any(word in attributes.get('onclick','') for word in ('openAxIdentity','openLeaderboard','toggleAPICall','showFullDetails')))
        if tag == 'script':
            src = attributes.get('src','')
            remove = src not in SCRIPTS and not src.startswith('libs/')
        if tag == 'link':
            remove = attributes.get('href','').startswith(('http','//','flight-activity/'))
        if remove:
            if tag not in VOID: self.skip.append(tag)
            return
        self.out.append('<' + tag + ''.join(' ' + k + ('' if v is None else '="' + html.escape(v, quote=True) + '"') for k,v in attrs) + '>')
    def handle_endtag(self, tag):
        if self.skip:
            if tag == self.skip[-1]: self.skip.pop()
            return
        self.out.append(f'</{tag}>')
    def handle_startendtag(self, tag, attrs): self.handle_starttag(tag, attrs)
    def handle_data(self, text):
        if not self.skip: self.out.append(text)
    def handle_entityref(self, name):
        if not self.skip: self.out.append('&' + name + ';')
    def handle_charref(self, name):
        if not self.skip: self.out.append('&#' + name + ';')
    def handle_decl(self, text): self.out.append('<!' + text + '>')


def replace_once(text, old, new):
    if text.count(old) != 1: raise ValueError(f'upstream patch anchor changed: {old[:70]}')
    return text.replace(old, new)


def build(output, database):
    output.mkdir(parents=True, exist_ok=True)
    # Fresh staging directory required; never recursively delete caller paths.
    if any(output.iterdir()): raise ValueError('output directory must be empty')
    shutil.copytree(ROOT/'html', output, dirs_exist_ok=True)
    for path in output.rglob('*.tmpl'): path.unlink()
    for folder in ('flight-activity','leaderboard'):
        if (output/folder).exists(): shutil.rmtree(output/folder)
    for path in output.glob('*turnstile*'): path.unlink()
    parser = LocalHTML()
    parser.feed((ROOT/'html/index.html').read_text(encoding='utf-8'))
    page = ''.join(parser.out)
    page = page.replace('<script src="early.js">', '<script>let databaseFolder="db-current";</script><script src="early.js">')
    page = page.replace('</head>', '<link rel="stylesheet" href="bridge.css"></head>')
    page = page.replace('</body>', '<script src="bridge.js"></script></body>')
    page = re.sub(r'<title>.*?</title>', '<title>Local aircraft · Home Assistant</title>', page)
    (output/'index.html').write_text(page, encoding='utf-8')
    early = (output/'early.js').read_text(encoding='utf-8')
    early = replace_once(early, 'let aggregator = true;', 'let aggregator = false;')
    early = early.replace('    aggregator = true;', '    aggregator = false;')
    # Reject unsupported hosted modes before their early requests are scheduled.
    early = replace_once(early, 'const feed = usp.get(\'feed\');', """
for (const key of ['feed','uuid','replay','heatmap','showtrace','reapi','globe','customtiles','tfrs','uk_advisory']) usp.params.delete(key);
const feed = null;""")
    (output/'early.js').write_text(early, encoding='utf-8')
    script = (output/'script.js').read_text(encoding='utf-8')
    script = replace_once(script, 'function processReceiverUpdate(data, init) {', '''function processReceiverUpdate(data, init) {
    if (!init && data.ha_bridge && typeof haBridgeApply === 'function') haBridgeApply(data.ha_bridge);
    if (window.haBridgeExpired) return;''')
    script = replace_once(script, '            if (++notNewCounter > 2) {', '            if (!data.ha_bridge && ++notNewCounter > 2) {')
    (output/'script.js').write_text(script, encoding='utf-8')
    for source in (ROOT/'tar1090/frontend').iterdir(): shutil.copy2(source, output/source.name)
    shutil.copytree(database/'db', output/'db-current', dirs_exist_ok=True)
    for required in ('ranges.js',):
        if not (output/'db-current'/required).exists(): raise ValueError('database incomplete')
    # Hash top-level assets only; dependency replacements happen before script hash.
    mapping = {}
    for path in sorted(output.iterdir()):
        if path.suffix not in ('.js','.css') or path.name in ('config.js','script.js'): continue
        # Workers are referenced from early.js: keep their names stable within versioned image.
        if path.name.endswith('Worker.js'): continue
        new = path.stem + '_' + hashlib.sha256(path.read_bytes()).hexdigest()[:16] + path.suffix
        mapping[path.name] = new
        path.rename(output/new)
    script = (output/'script.js').read_text(encoding='utf-8')
    page = (output/'index.html').read_text(encoding='utf-8')
    for old,new in mapping.items():
        page = page.replace('"'+old+'"', '"'+new+'"')
        script = script.replace('"'+old+'"','"'+new+'"').replace("'"+old+"'", "'"+new+"'")
    (output/'script.js').write_text(script, encoding='utf-8')
    name = 'script_' + hashlib.sha256((output/'script.js').read_bytes()).hexdigest()[:16] + '.js'
    (output/'script.js').rename(output/name)
    page = page.replace('"script.js"','"'+name+'"')
    (output/'index.html').write_text(page, encoding='utf-8')
    for ref in re.findall(r'(?:src|href)="([^"?#]+)', page):
        if ref.startswith(('http','//','#','mailto:')): continue
        if not (output/ref).exists():
            # Anchor/navigation links are not asset references.
            if re.search(r'\.(js|css|png|svg|ico)$',ref): raise ValueError(f'missing asset: {ref}')
    if re.search(r'<script[^>]+src="https?://', page): raise ValueError('external executable dependency')
    for path in output.glob('*.js'):
        if re.search(r'__[A-Z][A-Z_]+__', path.read_text(encoding='utf-8')): raise ValueError(f'unresolved template: {path.name}')
    shutil.copy2(ROOT/'LICENSE', output/'LICENSE.txt')
    (output/'version.json').write_text(json.dumps(json.loads((ROOT/'tar1090/versions.json').read_text())), encoding='utf-8')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--database', type=Path, required=True)
    args = p.parse_args()
    build(args.output, args.database)
