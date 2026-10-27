"""Publish only the generated snapshot to gh-pages. Never stage the parent repo."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from build import ROOT, build, choose_directories


def run(*args, cwd=ROOT, input=None, check=True):
    result = subprocess.run(args, cwd=cwd, input=input, text=True, encoding='utf-8',
                            capture_output=True, env={**os.environ, 'GIT_TERMINAL_PROMPT':'0', 'GCM_INTERACTIVE':'never'})
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f'{args[0]} failed')
    return result


def publish():
    dist = build()
    remote = run('git', 'remote', 'get-url', 'origin', cwd=ROOT.parent).stdout.strip()
    # Keep credentials out of URLs and process arguments.
    import re
    match = re.fullmatch(r'https://github\.com/([^/]+)/([^/]+?)(?:\.git)?', remote)
    if not match:
        raise ValueError('Ожидается origin вида https://github.com/owner/repository.git')
    owner, repo = match.groups()
    cred = run('git', 'credential', 'fill', input='protocol=https\nhost=github.com\n\n')
    fields = dict(line.split('=', 1) for line in cred.stdout.splitlines() if '=' in line)
    token = fields.get('password')
    if not token:
        raise RuntimeError('Нет сохранённого входа GitHub в Git Credential Manager.')

    def api(method, endpoint, body=None):
        request = Request('https://api.github.com'+endpoint, method=method,
                          data=json.dumps(body).encode() if body is not None else None,
                          headers={'Authorization':'Bearer '+token, 'Accept':'application/vnd.github+json',
                                   'X-GitHub-Api-Version':'2022-11-28', 'Content-Type':'application/json'})
        with urlopen(request, timeout=45) as response:
            data = response.read()
            return json.loads(data) if data else {}

    endpoint = f'/repos/{owner}/{repo}/pages'
    existing = None
    try:
        existing = api('GET', endpoint)
    except HTTPError as error:
        if error.code != 404:
            raise
    if existing and existing.get('source') != {'branch':'gh-pages', 'path':'/'}:
        raise RuntimeError('В репозитории уже настроен другой сайт Pages; его настройки не изменены.')
    checkout = (ROOT / '.publish').resolve()
    if checkout.parent != ROOT or checkout.name != '.publish':
        raise ValueError('Неверная папка публикации.')
    checkout.mkdir(exist_ok=True)
    run('git', 'init', str(checkout))
    run('git', 'remote', 'remove', 'origin', cwd=checkout, check=False)
    run('git', 'remote', 'add', 'origin', remote, cwd=checkout)
    branches = run('git', 'ls-remote', '--heads', 'origin', 'gh-pages', cwd=checkout).stdout.strip()
    parent = None
    if branches:
        run('git', 'fetch', 'origin', 'gh-pages', cwd=checkout)
        parent = run('git', 'rev-parse', 'FETCH_HEAD', cwd=checkout).stdout.strip()
        run('git', 'read-tree', parent, cwd=checkout)
    else:
        run('git', 'read-tree', '--empty', cwd=checkout)
    run('git', '--work-tree='+str(dist), 'add', '--all', cwd=checkout)
    tree = run('git', 'write-tree', cwd=checkout).stdout.strip()
    if parent and tree == run('git', 'rev-parse', parent+'^{tree}', cwd=checkout).stdout.strip():
        print('Сайт уже содержит эту сборку.')
    else:
        for field, fallback in [('name', 'Markdown Cards'), ('email', 'cards@users.noreply.github.com')]:
            value = run('git', 'config', 'user.'+field, cwd=ROOT.parent, check=False).stdout.strip() or fallback
            run('git', 'config', 'user.'+field, value, cwd=checkout)
        args = ['git','commit-tree',tree]
        if parent:
            args += ['-p',parent]
        commit = run(*args, cwd=checkout, input='Update Markdown cards\n').stdout.strip()
        run('git', 'push', 'origin', commit+':refs/heads/gh-pages', cwd=checkout)
    if not existing:
        try:
            existing = api('POST', endpoint, {'build_type':'legacy', 'source':{'branch':'gh-pages','path':'/'}})
        except HTTPError as error:
            if error.code != 409:
                raise
            # GitHub may enable Pages automatically on the first gh-pages push.
            existing = api('GET', endpoint)
            if existing.get('source') != {'branch':'gh-pages', 'path':'/'}:
                raise RuntimeError('GitHub включил Pages с неожиданными настройками.')
    url = existing.get('html_url') or f'https://{owner}.github.io/{repo}/'
    print('Отправлено в GitHub Pages: '+url, flush=True)
    print('Публикация GitHub обычно занимает несколько минут. Исходные заметки не изменены.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Обновить Markdown-карточки на GitHub Pages')
    parser.add_argument('--choose', action='store_true', help='Выбрать локальные папки перед публикацией')
    parser.add_argument('--local', action='store_true', help='Только собрать, без публикации')
    args = parser.parse_args()
    try:
        if args.choose and not choose_directories():
            print('Выбор отменён. Настройки и сайт не изменены.')
        elif args.local:
            build()
        else:
            publish()
    except Exception as error:
        print(f'Ошибка: {error}', flush=True)
        raise SystemExit(1)
