#!/usr/bin/env python3
"""Проверки поведения решения (не smoke). Нужен поднятый compose на :5173."""
import http.cookiejar
import json
import sys
import urllib.error
import urllib.request

base = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:5173').rstrip('/')


def client():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(opener, path, body=None, csrf='', method=None):
    headers = {'Content-Type': 'application/json'}
    if csrf:
        headers['X-CSRF-Token'] = csrf
    data = None if body is None else json.dumps(body).encode()
    if method is None:
        method = 'POST' if data is not None else 'GET'
    req = urllib.request.Request(base + '/api' + path, data=data, headers=headers, method=method)
    try:
        with opener.open(req, timeout=20) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        raw = error.read().decode('utf-8', errors='replace')
        try:
            payload = json.loads(raw) if raw else {}
        except ValueError:
            payload = {'raw': raw}
        return error.code, payload


def login(opener, role):
    status, data = call(opener, '/demo/login', {'role': role})
    assert status == 200, (role, status, data)
    assert data.get('csrf'), data
    return data


def main():
    # --- исходный баг: GET #103 без source раньше давал 500 ---
    editor = client()
    eg = login(editor, 'editor')
    csrf = eg['csrf']
    editor_id = eg['employee']['id']

    status, detail103 = call(editor, '/tickets/103')
    assert status == 200, detail103
    assert detail103['ticket']['id'] == 103, detail103
    assert detail103['ticket']['source'] is None, detail103
    print('ok: null source (#103) - was 500, now 200 + source=null')

    # --- исходный баг: viewer мог POST смену источника ---
    before = call(editor, '/tickets/102')[1]
    src_before = before['ticket']['source']['id']

    viewer = client()
    vg = login(viewer, 'viewer')
    status, denied = call(
        viewer,
        '/tickets/102/source',
        {'source_id': 1, 'employee_id': editor_id, 'role': 'editor'},
        csrf=vg['csrf'],
    )
    assert status == 403, (status, denied)
    after = call(editor, '/tickets/102')[1]
    assert after['ticket']['source']['id'] == src_before, after
    print('ok: viewer POST -> 403, data unchanged (fake employee_id in body ignored)')

    # --- архив только чтение ---
    hist104 = len(call(editor, '/tickets/104')[1]['history'])
    status, archived = call(editor, '/tickets/104/source', {'source_id': 1}, csrf=csrf)
    assert status == 403, (status, archived)
    assert len(call(editor, '/tickets/104')[1]['history']) == hist104
    print('ok: archived #104 -> 403')

    # --- нет заявки раньше, чем кривой source (порядок ТЗ) ---
    status, missing = call(editor, '/tickets/99999/source', {'source_id': 'nope'}, csrf=csrf)
    assert status == 404, (status, missing)
    print('ok: missing ticket -> 404 (even with bad source_id)')

    # --- невалидный ввод ---
    for bad in ('2', 2.5, None):
        status, err = call(editor, '/tickets/102/source', {'source_id': bad}, csrf=csrf)
        assert status == 400, (bad, status, err)
    status, err = call(editor, '/tickets/102/source', {}, csrf=csrf)
    assert status == 400, (status, err)
    status, err = call(editor, '/tickets/102/source', {'source_id': 999}, csrf=csrf)
    assert status == 400, (status, err)
    print('ok: invalid source -> 400')

    # --- идемпотентность ---
    detail102 = call(editor, '/tickets/102')[1]
    current = detail102['ticket']['source']['id']
    hist_len = len(detail102['history'])
    status, same = call(editor, '/tickets/102/source', {'source_id': current}, csrf=csrf)
    assert status == 200, (status, same)
    assert len(same['history']) == hist_len, same
    assert same['ticket']['source']['id'] == current
    print('ok: same source -> 200, no new history row')

    # --- happy path: смена и откат ---
    other = 1 if current != 1 else 3
    status, changed = call(editor, '/tickets/102/source', {'source_id': other}, csrf=csrf)
    assert status == 200, (status, changed)
    assert changed['ticket']['source']['id'] == other, changed
    assert len(changed['history']) == hist_len + 1, changed
    newest = changed['history'][0]
    assert newest['employee_id'] == editor_id, newest
    assert newest['old_source_id'] == current, newest
    assert newest['new_source_id'] == other, newest
    assert newest.get('created_at'), newest

    # вернём как было, чтобы не мешать ручным прогонам
    status, restored = call(editor, '/tickets/102/source', {'source_id': current}, csrf=csrf)
    assert status == 200 and restored['ticket']['source']['id'] == current, restored
    print('ok: source change + history from session')

    # --- 401 без сессии ---
    bare = client()
    status, unauth = call(bare, '/tickets')
    assert status == 401, (status, unauth)
    print('ok: no session -> 401')

    print('PASS: test_sol - rights, null source, archive, validation, idempotent, history')


if __name__ == '__main__':
    try:
        main()
    except AssertionError as error:
        print('FAIL:', error, file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('FAIL:', error, file=sys.stderr)
        sys.exit(1)
