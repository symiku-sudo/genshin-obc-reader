"""Chinese prose extraction. Never flatten unknown component data into the corpus."""
import html
import re
from datetime import datetime, timezone
from html.parser import HTMLParser

PARSER_VERSION = 6
SOURCE = 'https://baike.mihoyo.com/ys/obc/'

class TextExtractionError(ValueError):
    def __init__(self, message, audit):
        super().__init__(message)
        self.audit = audit
        self.needs_review = any(x['status'] == 'review' for x in audit)


class ProseParser(HTMLParser):
    boundaries = set('p div br hr h1 h2 h3 h4 h5 h6 li tr td th blockquote section article pre'.split())
    blocked = set('script style iframe object svg math template audio video'.split())

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.blocked:
            self.skip += 1
        elif not self.skip and tag in self.boundaries:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in self.blocked:
            self.skip = max(0, self.skip - 1)
        elif not self.skip and tag in self.boundaries:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def plain(value):
    if value is None:
        return ''
    if isinstance(value, list):
        return '\n'.join(filter(None, (plain(v) for v in value)))
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ''
    parser = ProseParser()
    parser.feed(str(value).replace('\\"', '"'))
    return '\n'.join(line.strip() for line in ''.join(parser.parts).replace('\xa0', ' ').splitlines() if line.strip())


def prose_html(text):
    return ''.join('<p>' + html.escape(line) + '</p>' for line in text.splitlines() if line.strip())


# Explicit exclusions, not a test for digits: numbers inside stories are preserved.
EXCLUDED_COMPONENTS = {
    'equipment_base_info', 'equipment_growth_info', 'role_ascension',
    'recommend', 'strategy', 'map_desc', 'business_card', 'timeline_base_info',
    'role_relation', 'base_info', 'rich_base_info', 'card_base_info',
}
NON_PROSE_MODULE = re.compile(
    r'攻略|推荐|搭配|成长|数值|突破|任务奖励|相关任务|地图|分布|天赋演示|角色展示|'
    r'角色CV|媒体资料|宣发时间轴|关联词条|特殊料理|效果描述|获取途径|获得方式'
)
# These can contain prose mixed with gameplay mechanics; require dedicated handling.
REVIEW_COMPONENTS = {'multi_table'}
PROSE_ATTRS = {'描述', '介绍', '简介', '故事', '背景故事', '作者'}
SETTING_ATTRS = {'生日', '所属', '命之座', '称号', '身份'}
ZH_LABELS = {'汉语', '中文', '简体中文', '简中', 'zh-cn', 'zh_cn', 'zh-hans', 'cn'}


def classify(title, category):
    if '剧情' in title or '对话' in title or '对白' in title:
        return '对白'
    if '语音' in title or '配音' in title:
        return '语音'
    if '邮件' in title:
        return '邮件'
    if '故事' in title or title == '神之眼':
        return '故事'
    if '书籍' in category:
        return '书籍'
    return '描述'


def ordered_modules(page):
    """Use the site's layout order (raw modules can scramble book volumes)."""
    modules = page.get('modules') or []
    lookup = {str(m.get('id')): (i, m) for i, m in enumerate(modules)}
    seen = set()
    for tab in (page.get('template_layout') or {}).get('tab', []):
        tab_name = plain(tab.get('tab_name', ''))
        if re.fullmatch(r'页签\d+', tab_name):
            tab_name = ''
        for group in tab.get('module_group', []):
            context = plain(group.get('name', ''))
            if not context:
                for ref in group.get('module', []):
                    found = lookup.get(str(ref.get('id')))
                    if found and any(c.get('component_id') == 'base_info' for c in found[1].get('components', [])):
                        context = plain(found[1].get('name', ''))
                        break
            for ref in group.get('module', []):
                key = str(ref.get('id'))
                if key in lookup and key not in seen:
                    seen.add(key)
                    index, module = lookup[key]
                    yield index, module, tab_name, context
    # Unreferenced modules aren't silently lost; they remain auditable at the end.
    for index, module in enumerate(modules):
        if str(module.get('id')) not in seen:
            yield index, module, '', ''


def dialogue_blocks(data):
    """Traverse explicit dialogue edges, never dictionary order or arbitrary fields."""
    trees = data.get('list') or [data]
    if not isinstance(trees, list):
        raise ValueError('invalid dialogue list')
    result = []
    for ti, tree in enumerate(trees):
        nodes, edges = tree.get('contents'), tree.get('child_ids')
        root = tree.get('root_id')
        if not root and not nodes and not edges:
            continue
        if not isinstance(nodes, dict) or not isinstance(edges, dict) or (root not in nodes and root not in edges):
            raise ValueError('invalid dialogue root')
        prefix = f'list[{ti}].' if data.get('list') else ''
        stack, reached, visits = [(root, (), ())], set(), 0
        while stack:
            key, ancestors, choices = stack.pop()
            visits += 1
            if key in ancestors or (key not in nodes and key != root) or visits > 10000:
                raise ValueError('cyclic, missing or oversized dialogue')
            if key in nodes:
                reached.add(key)
            node = nodes.get(key, {})
            option = plain(node.get('option'))
            route = choices + ((option,) if option else ())
            title = '交互文本' + (f' · 第 {ti + 1} 组' if len(trees) > 1 else '')
            if route:
                title += ' · ' + ' → '.join(route)
            field = prefix + f'contents[{key!r}]'
            if option:
                result.append((title + ' · 选项', node['option'], field + '.option'))
            if plain(node.get('dialogue')):
                result.append((title, node['dialogue'], field + '.dialogue'))
            children = edges.get(key, [])
            if not isinstance(children, list) or any(not isinstance(x, str) for x in children):
                raise ValueError('invalid dialogue edges')
            stack.extend((child, ancestors + (key,), route) for child in reversed(children))
        if reached != set(nodes) or set(edges) - set(nodes) - {root}:
            raise ValueError('unreachable dialogue nodes')
    return result


def extract_tables(data):
    """Only explicit prose columns; known recipe/growth schemas are not prose."""
    blocks, unknown = [], False
    technical = {'详细属性','烹饪材料','料理效果（美味）','角色展示','道具展示','合成材料','描述',
                 '食材展示','加工材料','用途','使用效果','料理名称','合成素材','数量','料理展示',
                 '成品展示','锻造材料','木材展示','价格','图谱展示','需要鱼类','升级材料',
                 '突破材料','武器展示','怪物展示','天赋','合成所需材料'}
    for ti, table in enumerate(data.get('tables', [])):
        headers = [plain(h) for h in table.get('header', [])]
        rows = table.get('row', [])
        if headers in (['故事','插图','文案'], ['曲调','插图','文案']):
            for ri, row in enumerate(rows):
                if len(row) != 3: raise ValueError('invalid prose table row')
                if plain(row[2]): blocks.append((plain(row[0]) or '正文', row[2], f'tables[{ti}].row[{ri}][2]'))
        elif headers and set(headers) <= technical and set(headers) & {'数量','烹饪材料','合成材料','加工材料','锻造材料','价格','升级材料','突破材料','天赋','合成所需材料','怪物展示','料理效果（美味）'}:
            continue
        elif headers == ['序号','图片'] and all(len(row)==2 and not plain(row[1]) for row in rows):
            continue
        elif not any(plain(cell) for row in rows for cell in row) and all(h in ('','名称','介绍','描述','标题') for h in headers):
            continue
        elif headers == ['',''] and rows and all(len(row)==2 and re.fullmatch(r'\d+级\*\d+(?:；\d+级\*\d+)*', plain(row[1])) for row in rows):
            continue
        else:
            unknown = True
    return blocks, unknown


def extract_page(page):
    import json
    category = ' / '.join(m['name'] for m in (page.get('menus') or [])) or page.get('menu_name') or '未分类'
    sections, audit, warnings = [], [], []
    for index, module, tab, context in ordered_modules(page):
        name = plain(module.get('name', ''))
        for ci, component in enumerate(module.get('components') or []):
            kind = component.get('component_id', 'unknown')
            path = f'modules[{index}].components[{ci}]'
            record = {'module_id': str(module.get('id', index)), 'component': kind, 'path': path, 'status': '', 'reason': '', 'sections': []}
            audit.append(record)
            if module.get('is_hidden'):
                record.update(status='excluded', reason='hidden_module')
                continue
            if (kind == 'multi_table' and name == '相关信息' and category == '背包') or NON_PROSE_MODULE.search(name) or kind in EXCLUDED_COMPONENTS or kind == 'role_talent' or name == '命之座':
                record.update(status='excluded', reason='not_narrative_text')
                continue
            try:
                data = json.loads(component['data']) if isinstance(component.get('data'), str) else component.get('data')
                if not isinstance(data, dict):
                    raise ValueError('component data must be object')
                blocks = []
                def add(title, value, field, text_type=None):
                    text = plain(value)
                    if text:
                        blocks.append({'title': plain(title) or name or '正文', 'text': text,
                                       'source_field': path + '.data.' + field,
                                       'text_type': text_type or classify(name, category)})

                if kind == 'material_base_info':
                    for ai, attr in enumerate(data.get('attr', [])):
                        key = plain(attr.get('key', '')).strip(' ：:')
                        if key in PROSE_ATTRS:
                            title = plain(data.get('name')) or name or page['name']
                            add(title + (' · ' + key if key != '描述' else ' · 简述'), attr.get('value'), f'attr[{ai}].value', '描述')
                elif kind == 'artifact_list_v2':
                    title = plain(data.get('name', {}).get('value')) or name
                    add(title + ' · 简述', data.get('desc', {}).get('value'), 'desc.value', '描述')
                    add(title + ' · 故事', data.get('story', {}).get('value'), 'story.value', '故事')
                elif kind == 'good_desc':
                    rich = data.get('rich_text', '')
                    # Weapon descriptions share a rich-text field with refinements.
                    # Only split when the upstream provides an explicit separator.
                    pieces = re.split(r'<hr\b[^>]*>', rich, flags=re.I)
                    if len(pieces) > 1 and re.search(r'精炼|%|％', plain(pieces[0])):
                        add('武器简述', ''.join(pieces[1:]), 'rich_text:after_hr', '描述')
                    elif re.search(r'精炼[（(]|精炼.*阶', plain(rich)):
                        record.update(status='review', reason='mixed_weapon_effect_without_separator')
                    else:
                        add('武器简述', rich, 'rich_text', '描述')
                elif kind == 'interactive_dialogue':
                    for title, value, field in dialogue_blocks(data):
                        add(title, value, field, '交互文本')
                elif kind == 'collapse_panel':
                    add(name or '正文', data.get('rich_text'), 'rich_text')
                    if not blocks and re.search(r'<(?:iframe|img|video|audio)\b', data.get('rich_text', ''), re.I):
                        record.update(status='excluded', reason='media_without_text')
                elif kind == 'role_base_info':
                    for ai, attr in enumerate(data.get('attr', [])):
                        key = plain(attr.get('key', '')).strip(' ：:')
                        if key in SETTING_ATTRS:
                            add(key, attr.get('value'), f'attr[{ai}].value', '资料')
                elif kind == 'role_voice':
                    tabs = data.get('list', [])
                    chinese = [(i, t) for i, t in enumerate(tabs) if plain(t.get('tab_name', '')).casefold() in ZH_LABELS]
                    if not chinese:
                        has_text = any(plain(v.get('content')) or plain(v.get('name')) for t in tabs for v in t.get('table', []))
                        record.update(status='review' if has_text else 'excluded', reason='no_explicit_chinese_voice_tab' if has_text else 'empty_voice_template')
                    seen = set()
                    for ti, voice_tab in chinese:
                        for vi, voice in enumerate(voice_tab.get('table', [])):
                            key = (plain(voice.get('name')), plain(voice.get('content')))
                            if key in seen:
                                continue
                            seen.add(key)
                            add(key[0] or '语音文字', voice.get('content'), f'list[{ti}].table[{vi}].content', '语音')
                elif kind == 'multi_table':
                    table_blocks, unknown = extract_tables(data)
                    for title, value, field in table_blocks:
                        add(title, value, field, '正文')
                    if unknown:
                        record.update(status='review', reason='unadapted_component')
                    elif not table_blocks:
                        record.update(status='excluded', reason='table_without_narrative_text')
                else:
                    record.update(status='review', reason='unadapted_component')
                for bi, block in enumerate(blocks):
                    section = {'id': f'section-{index}-{ci}-{bi}', 'module_id': str(module.get('id', index)),
                               'tab': tab, 'context': context, **block, 'html': prose_html(block['text'])}
                    sections.append(section)
                    record['sections'].append(section['id'])
                if blocks and record['status'] != 'review':
                    record['status'] = 'included'
                elif not record['status']:
                    record.update(status='excluded', reason='no_requested_text_fields')
            except (ValueError, TypeError, KeyError, AttributeError):
                record.update(status='review', reason='malformed_component')
    reviews = sum(x['status'] == 'review' for x in audit)
    if reviews:
        warnings.append(f'有 {reviews} 个模块尚待文本适配，未自动混入正文；可通过原词条核对。')
    if not sections:
        raise TextExtractionError('此词条未提取到所需中文文本；属性、材料、图片与玩法说明不收录', audit)
    return {'id': str(page['id']), 'title': plain(page['name']), 'category': category,
            'source': SOURCE + 'content/' + str(page['id']) + '/detail', 'version': page.get('version'),
            'parser_version': PARSER_VERSION, 'content_mode': 'zh-prose', 'language': 'zh-CN',
            'fetched_at': datetime.now(timezone.utc).isoformat(), 'sections': sections,
            'warnings': warnings, 'extraction': audit}
