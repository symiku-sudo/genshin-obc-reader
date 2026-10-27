"""Verified official category manifests; no guesswork based on search results."""
import hashlib
import json
import re
from datetime import datetime, timezone
import core

CATEGORIES = {'books': ('书籍', '68'), 'weapons': ('武器', '5'), 'artifacts': ('圣遗物', '218'), 'map_texts': ('地图文本', '251'), 'characters': ('角色', '25'), 'food': ('食物', '21'), 'inventory': ('背包', '13')}


def now():
    return datetime.now(timezone.utc).isoformat()


def parse_manifest(data, category):
    name, channel_id = CATEGORIES[category]
    roots = data.get('list')
    if not isinstance(roots, list) or len(roots) != 1:
        raise ValueError('目录结构变化，未替换已有目录')
    root = roots[0]
    if str(root.get('id')) != channel_id or root.get('name') != name:
        raise ValueError('目录分类不匹配，未替换已有目录')
    if root.get('entry_limit') != 0 or root.get('children') or root.get('hidden'):
        raise ValueError('目录可能截断或出现子分类，需要重新适配')
    if not isinstance(root.get('list'), list) or not root['list']:
        raise ValueError('目录意外为空，未替换已有目录')
    unique, duplicates = {}, 0
    for item in root['list']:
        entry_id = str(item.get('content_id', ''))
        title = core.clean(item.get('title', ''))[1]
        if not re.fullmatch(r'\d{1,12}', entry_id) or not title:
            raise ValueError('目录含无效词条，未替换已有目录')
        if entry_id in unique:
            if unique[entry_id]['title'] != title:
                raise ValueError('重复 ID 的名称冲突，需要核对目录')
            duplicates += 1
        unique[entry_id] = {'id': entry_id, 'title': title}
    items = sorted(unique.values(), key=lambda x: int(x['id']))
    return {'category': category, 'name': name, 'channel_id': channel_id,
            'fetched_at': now(), 'raw_count': len(root['list']), 'duplicates': duplicates,
            'items': items, 'digest': hashlib.sha256(json.dumps(items, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            'scope': '原站当前公开分类目录；不含未列出或隐藏词条'}


def fetch_manifest(category):
    if category not in CATEGORIES:
        raise ValueError('不支持的分类')
    data = core.upstream_request('/common/blackboard/ys_obc/v1/home/content/list',
        {'channel_id': CATEGORIES[category][1], 'app_sn': 'ys_obc'}, static=True)
    return parse_manifest(data, category)
