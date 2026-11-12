"""Task-only parsing. Existing eight-category section IDs and parser version stay stable."""
import hashlib
import heapq
import json
import re
from datetime import datetime, timezone

TASK_PARSER_VERSION = 1
TASK_CATEGORIES = {'archon': '魔神任务', 'world': '世界任务', 'story': '传说任务',
                   'hangout': '邀约任务', 'event': '限时任务'}


def tags_from_ext(ext):
    try:
        if isinstance(ext, str): ext = json.loads(ext)
        if 'fe_ext' in ext: return tags_from_ext(ext['fe_ext'])
        value = ext.get('c_43', {}).get('filter', {}).get('text', '[]')
        if isinstance(value, str):
            try: value = json.loads(value)
            except json.JSONDecodeError: value = json.loads(value.replace('\\"', '"'))
        return [v for v in value if isinstance(v, str)]
    except (ValueError, TypeError, AttributeError):
        return []


def metadata(title, ext):
    tags = tags_from_ext(ext)
    types = [t.split('/', 1)[1] for t in tags if t.startswith('任务类型/')]
    regions = [t.split('/', 1)[1] for t in tags if t.startswith('任务区域/')]
    # The explicit upstream title identifies hangouts; arbitrary mentions don't.
    if title.startswith('邀约事件·'): kind = 'hangout'
    elif '限时任务' in types: kind = 'event'
    else: kind = next((k for k, v in TASK_CATEGORIES.items() if v in types), '')
    return {'kind': kind, 'types': types, 'regions': regions,
            'group': ' / '.join(regions) or '未标地区', 'tags': tags}


def is_task(page):
    return any(str(m.get('id')) == '43' for m in (page.get('menus') or [])) or page.get('menu_name') == '任务'


def section_id(module, component, key):
    digest = hashlib.sha256(f'{module}:{component}:{key}'.encode()).hexdigest()[:24]
    return 'task-' + digest


def graph_nodes(tree, allow_orphans=False):
    """Stable topological traversal: every shared node once, explicit edges retained."""
    nodes, edges, root = tree.get('contents') or {}, tree.get('child_ids') or {}, tree.get('root_id')
    if not root and not nodes and not edges: return []
    if not isinstance(nodes, dict) or not isinstance(edges, dict) or not root or (root not in nodes and root not in edges):
        raise ValueError('对白起点缺失')
    if len(nodes) > 20000: raise ValueError('对白节点过多')
    rank, stack = {}, [root]
    while stack:
        key = stack.pop()
        if key in rank: continue
        if key not in nodes and key != root: raise ValueError('对白引用了缺失节点')
        if key in nodes and not isinstance(nodes[key], dict): raise ValueError('对白节点格式异常')
        rank[key] = len(rank)
        children = edges.get(key, [])
        if not isinstance(children, list) or any(not isinstance(c, str) for c in children):
            raise ValueError('对白分支格式异常')
        stack.extend(reversed(list(dict.fromkeys(children))))
    if not allow_orphans and (set(nodes) - set(rank) or set(edges) - set(rank)): raise ValueError('存在未连接的对白节点')
    degree = dict.fromkeys(rank, 0)
    for key in rank:
        for child in set(edges.get(key, [])): degree[child] += 1
    ready = [(rank[k], k) for k in rank if degree[k] == 0]; heapq.heapify(ready)
    result = []
    while ready:
        _, key = heapq.heappop(ready)
        result.append((key, nodes.get(key, {}), list(dict.fromkeys(edges.get(key, [])))))
        for child in set(edges.get(key, [])):
            degree[child] -= 1
            if degree[child] == 0: heapq.heappush(ready, (rank[child], child))
    if len(result) != len(rank): raise ValueError('对白分支存在循环')
    return result


def extract_task(page):
    from text_extract import plain, prose_html, ordered_modules, PARSER_VERSION, TextExtractionError
    meta = metadata(plain(page.get('name', '')), page.get('ext', {}))
    sections, audit, missing = [], [], []
    contexts, dialogue_contexts = set(), set()
    for index, module, tab, context in ordered_modules(page):
        name = plain(module.get('name', '')); context = context or tab or plain(page['name'])
        mid = str(module.get('id', index))
        if module.get('is_hidden'): continue
        for ci, component in enumerate(module.get('components') or []):
            kind = component.get('component_id', 'unknown')
            record = {'module_id': mid, 'component': kind, 'status': 'excluded', 'reason': 'not_narrative_text', 'sections': []}
            audit.append(record)
            def add(key, title, value, text_type='对白', links=None, plain_text=False):
                text = value if plain_text else plain(value)
                if not text: return None
                sid = section_id(mid, ci, key)
                sections.append({'id': sid, 'module_id': mid, 'tab': tab, 'context': context,
                    'title': title, 'text': text, 'html': prose_html(text), 'text_type': text_type,
                    'source_field': f'module[{mid}].{kind}.{key}', 'links': links or []})
                record['sections'].append(sid); record.update(status='included', reason='')
                return sid
            try:
                data = json.loads(component['data']) if isinstance(component.get('data'), str) else component.get('data')
                if not isinstance(data, dict): raise ValueError('模块格式异常')
                if kind == 'interactive_dialogue':
                    contexts.add(context)
                    trees = data.get('list') or [data]
                    if not isinstance(trees, list): raise ValueError('对白组格式异常')
                    errors = []
                    for ti, tree in enumerate(trees):
                        try:
                            graph = graph_nodes(tree, allow_orphans=True)
                            if not graph: errors.append('对白组为空'); continue
                            reached = {k for k, _, _ in graph}
                            if (set(tree.get('contents') or {}) | set(tree.get('child_ids') or {})) - reached:
                                errors.append('来源含未连接节点，仅提取明确连线内的对白')
                            tree_key = tree['root_id']
                            content_keys = {k for k, n, _ in graph if plain(n.get('option')) or plain(n.get('dialogue'))}
                            # Nodes without prose still provide a navigable connection.
                            node_lookup = {k: n for k, n, _ in graph}
                            incoming = {k: 0 for k, _, _ in graph}
                            for _, _, children in graph:
                                for child in children: incoming[child] += 1
                            targets = {k: section_id(mid, ci, f'{tree_key}:{k}') for k, _, _ in graph}
                            for ni, (key, node, children) in enumerate(graph):
                                option = plain(node.get('option'))
                                value = '\n'.join(v for v in (option, plain(node.get('dialogue'))) if v)
                                text_type = '对白' if value else '分支导航'
                                if not value: value = '以下为可选分支。' if children else '此处原站未提供对白。'
                                label = option or (('共用剧情' if incoming[key] > 1 else '剧情段落') + f' · 第 {ti + 1} 组 · {ni + 1}')
                                links = [{'id': targets[ch], 'title': plain(node_lookup[ch].get('option')) or '后续剧情'} for ch in children]
                                add(f'{tree_key}:{key}', label, value, text_type, links=links, plain_text=True)
                            if content_keys: dialogue_contexts.add(context)
                            else: errors.append('对白组没有正文')
                        except (ValueError, TypeError, KeyError, AttributeError) as exc:
                            errors.append(f'第 {ti + 1} 组：{exc}')
                    if errors: raise ValueError('；'.join(errors))
                elif kind == 'collapse_panel':
                    rich = data.get('rich_text', '')
                    if name == '任务过程':
                        contexts.add(context)
                        # Intro paragraphs precede the explicit objective list.
                        intro = re.split(r'<(?:ul|ol)\b', rich, maxsplit=1, flags=re.I)[0]
                        intro = re.sub(r'<p\b[^>]*>[^<]*(?:详细路线|攻略推荐)[\s\S]*?</p>', '', intro, flags=re.I)
                        add('intro', '任务概述', intro, '概述')
                    elif re.search(r'剧情|对白|对话', name):
                        contexts.add(context)
                        text = plain(rich)
                        if meta['kind'] == 'hangout' and re.search(r'(?:^|\n)End\s*\d+', text, re.I):
                            endings = re.split(r'(?m)^(?=End\s*\d+)', text, flags=re.I)[1:]
                            for ending in endings:
                                title, _, body = ending.partition('\n')
                                add('ending:' + title, title, body, '结局短句', plain_text=True)
                            raise ValueError('来源仅有结局短句，缺少完整分支对白')
                        if re.search(r'路线攻略|攻略推荐|具体攻略', text):
                            raise ValueError('剧情栏目混有攻略，需核对后提取')
                        if add('prose', name, rich): dialogue_contexts.add(context)
                        else: raise ValueError('剧情模块没有正文')
                    elif name in ('任务描述', '任务介绍', '任务概述'):
                        add('intro', name, rich, '概述')
                    elif not name and plain(rich): raise ValueError('未命名文本模块待核对')
                elif kind not in ('base_info', 'rich_base_info', 'map_desc'):
                    raise ValueError('未知任务模块：' + kind)
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                record.update(status='review', reason=str(exc))
                missing.append({'context': context, 'module': name or kind, 'reason': str(exc)})
    for context in sorted(contexts - dialogue_contexts):
        missing.append({'context': context, 'module': '剧情对话', 'reason': '未提取到可读对白'})
    if not meta['kind']: missing.append({'context': '', 'module': '任务类型', 'reason': '来源未提供可识别的类型'})
    if not sections: raise TextExtractionError('任务尚无可提取的中文正文', audit)
    warnings = ['正文不完整：有缺失或待适配部分，请查看下方清单。'] if missing else []
    return {'id': str(page['id']), 'title': plain(page['name']),
        'category': TASK_CATEGORIES.get(meta['kind'], '任务（待分类）'),
        'source': 'https://baike.mihoyo.com/ys/obc/content/' + str(page['id']) + '/detail',
        'version': page.get('version'), 'parser_version': PARSER_VERSION, 'task_parser_version': TASK_PARSER_VERSION,
        'content_mode': 'zh-prose', 'language': 'zh-CN', 'fetched_at': datetime.now(timezone.utc).isoformat(),
        'sections': sections, 'warnings': warnings, 'extraction': audit, 'task': meta,
        'incomplete': bool(missing), 'missing': missing}


def task_sort_key(title):
    # Only explicit chapter/act labels define order. No inferred quest chronology.
    numbers = {'零':0,'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
    def numeric(value):
        if value.isdigit(): return int(value)
        if '十' in value:
            a,b=value.split('十',1);return numbers.get(a,1)*10+numbers.get(b,0)
        return numbers.get(value,99)
    key = title.replace('序章', '第零章')
    return re.sub(r'第([零一二三四五六七八九十0-9]+)(章|幕)', lambda m: '第'+str(numeric(m[1])).zfill(3)+m[2], key)
