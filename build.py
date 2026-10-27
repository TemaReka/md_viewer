"""Build a portable static snapshot. Python standard library only."""
from pathlib import Path
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import re
import shutil
import tempfile
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'sources.json'


def choose_directories():
    import tkinter as tk
    from tkinter import filedialog, messagebox
    window = tk.Tk()
    window.withdraw()
    paths = []
    while True:
        path = filedialog.askdirectory(title='Выберите папку с Markdown-файлами', initialdir=str(ROOT.parent))
        if not path:
            break
        paths.append(str(Path(path).resolve()))
        if not messagebox.askyesno('Папки', 'Добавить ещё одну папку?'):
            break
    window.destroy()
    if paths:
        config = json.loads(CONFIG.read_text(encoding='utf-8'))
        config['directories'] = paths
        CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return bool(paths)


def build():
    config = json.loads(CONFIG.read_text(encoding='utf-8-sig'))
    sources = [(ROOT / p).resolve() for p in config['directories']]
    if not sources:
        raise ValueError('Выберите хотя бы одну папку в sources.json.')
    records, seen = [], set()
    for source in sources:
        if not source.is_dir():
            raise FileNotFoundError(f'Папка не найдена: {source}')
        for path in sorted(source.rglob('*'), key=lambda p: p.as_posix().casefold()):
            if path.suffix.lower() != '.md' or not path.is_file():
                continue
            path = path.resolve()
            if path in seen or ROOT in path.parents:
                continue
            if any(part.startswith('.') for part in path.relative_to(source).parts):
                continue
            if any(fnmatch.fnmatch(path.name.casefold(), pattern.casefold()) for pattern in config.get('exclude', [])):
                continue
            markdown = path.read_text(encoding='utf-8-sig')
            if not markdown.strip():
                continue
            seen.add(path)
            base = source.parent if source.name == 'questions' else source
            folder = base.name + ('/questions' if source.name == 'questions' else '')
            relative = path.relative_to(source).parent.as_posix()
            if relative != '.':
                folder += '/' + relative
            # Workspace-relative identity survives moving the whole workspace.
            try:
                identity = path.relative_to(ROOT.parent).as_posix()
            except ValueError:
                identity = path.as_posix()
            card_id = hashlib.sha256(identity.encode()).hexdigest()[:16]
            title = re.search(r'^#\s+(.+?)\s*#*$', markdown, re.MULTILINE)
            records.append({'path': path, 'boundary': base, 'id': card_id, 'folder': folder,
                            'title': title.group(1) if title else path.stem.replace('-', ' '), 'markdown': markdown})
    if not records:
        raise ValueError('Нет непустых Markdown-файлов. Предыдущая сборка сохранена.')
    staging = tempfile.TemporaryDirectory(prefix='.cards-build-', dir=ROOT)
    dist = Path(staging.name)
    shutil.copytree(ROOT / 'web', dist, dirs_exist_ok=True)
    by_path = {r['path']: r['id'] for r in records}
    assets = dist / 'assets'
    assets.mkdir(exist_ok=True)

    def rewrite(url, record, image=False):
        parts = urlsplit(url)
        if parts.scheme or parts.netloc or not parts.path or url.startswith('#'):
            return url
        target = (record['path'].parent / unquote(parts.path)).resolve()
        if target in by_path and not image:
            return '#card:' + by_path[target]
        if target.suffix.lower() in {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.avif'}:
            if not target.is_relative_to(record['boundary']):
                raise ValueError(f'Изображение вне папки-источника: {target}')
            content = target.read_bytes()
            name = hashlib.sha256(content).hexdigest()[:20]+target.suffix.lower()
            (assets / name).write_bytes(content)
            return 'assets/'+name
        return url

    cards = []
    for record in records:
        # Preserve fenced code blocks verbatim; rewrite standard inline links/images elsewhere.
        chunks = re.split(r'(^```[^\n]*\n.*?^```[^\n]*$|^~~~[^\n]*\n.*?^~~~[^\n]*$)', record['markdown'], flags=re.MULTILINE | re.DOTALL)
        for i in range(0, len(chunks), 2):
            def inline(match):
                prefix, url, suffix = match.groups()
                return prefix + rewrite(url, record, prefix.startswith('!')) + suffix
            chunks[i] = re.sub(r'(!?\[[^\]\n]*\]\()<?([^\s<>]*?)>?(\s+"[^"\n]*"\)|\))', inline, chunks[i])
        cards.append({k: record[k] for k in ('id', 'folder', 'title')} | {'markdown': ''.join(chunks)})
    payload = {'updated': datetime.now(timezone.utc).isoformat(), 'cards': cards}
    temporary = dist / 'cards.json.tmp'
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    temporary.replace(dist / 'cards.json')
    (dist / '.nojekyll').touch()
    output = (ROOT / 'dist').resolve()
    if output.parent != ROOT or output.name != 'dist':
        raise ValueError('Неверная папка сборки.')
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(dist, output)
    staging.cleanup()
    dist = output
    print(f'Собрано {len(cards)} карточек из {len(set(c["folder"] for c in cards))} папок: {dist}', flush=True)
    return dist


if __name__ == '__main__':
    import sys
    if '--choose' not in sys.argv or choose_directories():
        build()
