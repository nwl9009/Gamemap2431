"""Convert Lua discovery data files to JSON for the satellite viewer."""
import json
import os
import re
import sys

def parse_lua_table(text):
    """Convert Lua table syntax to Python using character-level bracket tracking."""
    text = re.sub(r'--[^\n]*', '', text)  # strip comments
    text = re.sub(r'return\s*', '', text, count=1)
    text = text.replace('true', 'True').replace('false', 'False').replace('nil', 'None')
    # Convert keyed entries
    text = re.sub(r'\[(\d+)\]\s*=', r'\1:', text)
    text = re.sub(r'\["([^"]+)"\]\s*=', r'"\1":', text)
    text = re.sub(r'(\n\s*)(\w+)\s*=\s*', r'\1"\2": ', text)
    text = re.sub(r',(\s*})', r'\1', text)

    # Now convert Lua tables: { used as array (no keys, just values) -> []
    # Strategy: scan char by char, track brace depth, detect if a {} block
    # is an array (first non-whitespace content after { is { or a non-key value)
    out = []
    i = 0
    while i < len(text):
        if text[i] == '{':
            # Look ahead: is this an array? (contains { as first real content, or no "key":)
            j = i + 1
            while j < len(text) and text[j] in ' \t\r\n':
                j += 1
            if j < len(text) and text[j] == '{':
                out.append('[')
                # Mark this brace as array - we need to find its matching close
                # Push marker
                i += 1
                depth = 1
                while i < len(text) and depth > 0:
                    if text[i] == '{':
                        out.append('{')
                        depth += 1
                    elif text[i] == '}':
                        depth -= 1
                        if depth == 0:
                            # Remove trailing comma before ]
                            s = ''.join(out).rstrip()
                            if s.endswith(','):
                                out.clear()
                                out.append(s[:-1])
                            out.append(']')
                        else:
                            out.append('}')
                    else:
                        out.append(text[i])
                    i += 1
                continue
            else:
                out.append('{')
        else:
            out.append(text[i])
        i += 1

    text = ''.join(out)
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    try:
        return eval(text)
    except Exception as e:
        print(f"Parse error: {e}")
        print(text[:500])
        return None


def _tile_dist(ax, ay, bx, by):
    return ((ax - bx)**2 + (ay - by)**2)**0.5


def _filter_teleport_false_positives(teleports):
    """Remove spell/wand/command teleport false positives using heuristics.

    Filters applied:
    1. Shared destination: if 2+ entries from distinct sources (>10 tiles apart)
       land within 5 tiles of each other, they're spell/wand teleports TO a
       marked/clicked location. Remove all entries in that destination cluster.
    2. Long-range + low count: distance > 100 tiles with count == 1 is almost
       certainly Praesentis Trans or -port.
    3. Adjacent source merge: entries with sources within 5 tiles AND destinations
       within 5 tiles are the same real teleport observed from slightly different
       positions. Keep the one with the highest count.
    """
    if not teleports:
        return teleports

    # --- Pass 1: Shared destination clustering ---
    # Group entries whose destinations are within 5 tiles of each other
    dest_clusters = []  # list of [entry_indices]
    assigned = set()
    for i, t in enumerate(teleports):
        if i in assigned:
            continue
        cluster = [i]
        assigned.add(i)
        for j in range(i + 1, len(teleports)):
            if j in assigned:
                continue
            if _tile_dist(t['dstX'], t['dstY'],
                          teleports[j]['dstX'], teleports[j]['dstY']) <= 5:
                cluster.append(j)
                assigned.add(j)
        dest_clusters.append(cluster)

    # Mark clusters with 2+ entries from distinct source areas as false positives
    false_idx = set()
    for cluster in dest_clusters:
        if len(cluster) < 2:
            continue
        # Check if sources are spread out (>10 tiles between any pair)
        sources = [(teleports[i]['srcX'], teleports[i]['srcY']) for i in cluster]
        has_distinct = False
        for a in range(len(sources)):
            for b in range(a + 1, len(sources)):
                if _tile_dist(*sources[a], *sources[b]) > 10:
                    has_distinct = True
                    break
            if has_distinct:
                break
        if has_distinct:
            for i in cluster:
                false_idx.add(i)
                print(f"  [filter] Shared dest cluster: ({teleports[i]['srcX']},{teleports[i]['srcY']})"
                      f"->({teleports[i]['dstX']},{teleports[i]['dstY']}) removed")

    remaining = [t for i, t in enumerate(teleports) if i not in false_idx]

    # --- Pass 2: Long-range + single observation ---
    filtered = []
    for t in remaining:
        dist = _tile_dist(t['srcX'], t['srcY'], t['dstX'], t['dstY'])
        if dist > 100 and t['count'] <= 1:
            print(f"  [filter] Long-range single-obs: ({t['srcX']},{t['srcY']})"
                  f"->({t['dstX']},{t['dstY']}) dist={dist:.0f} removed")
            continue
        filtered.append(t)
    remaining = filtered

    # --- Pass 3: Adjacent source merge ---
    merged = []
    used = set()
    for i, t in enumerate(remaining):
        if i in used:
            continue
        best = t
        group = [i]
        for j in range(i + 1, len(remaining)):
            if j in used:
                continue
            if (_tile_dist(t['srcX'], t['srcY'],
                           remaining[j]['srcX'], remaining[j]['srcY']) <= 5 and
                _tile_dist(t['dstX'], t['dstY'],
                           remaining[j]['dstX'], remaining[j]['dstY']) <= 5):
                group.append(j)
                used.add(j)
                if remaining[j]['count'] > best['count']:
                    best = remaining[j]
        if len(group) > 1:
            print(f"  [filter] Merged {len(group)} adjacent entries at "
                  f"~({best['srcX']},{best['srcY']})->({best['dstX']},{best['dstY']})")
        used.add(i)
        merged.append(best)

    return merged


def convert_teleports(lua_file, out_file):
    with open(lua_file) as f:
        data = parse_lua_table(f.read())
    if not data:
        return

    teleports = []
    for key, info in data.items():
        # key format: "0:x,y"
        parts = key.split(':')
        layer = int(parts[0])
        sx, sy = map(int, parts[1].split(','))
        src = info.get('source', {})
        for dest in info.get('destinations', []):
            dx = dest.get('tileX', 0)
            dy = dest.get('tileY', 0)
            # Filter out walking - only keep jumps > 5 tiles distance
            dist = ((dx - sx)**2 + (dy - sy)**2)**0.5
            if dist <= 5:
                continue
            teleports.append({
                'srcX': sx, 'srcY': sy,
                'dstX': dx, 'dstY': dy,
                'srcHeight': src.get('tileHeight', 0),
                'dstHeight': dest.get('tileHeight', 0),
                'srcTileType': src.get('tileType', 0),
                'dstTileType': dest.get('tileType', 0),
                'count': dest.get('count', 1),
                'layer': layer,
            })

    pre_count = len(teleports)
    teleports = _filter_teleport_false_positives(teleports)

    with open(out_file, 'w') as f:
        json.dump({'teleports': teleports, 'count': len(teleports)}, f, indent=2)
    print(f"Teleports: {pre_count} raw -> {len(teleports)} after filtering -> {out_file}")


def convert_hazards(lua_file, out_file):
    with open(lua_file) as f:
        data = parse_lua_table(f.read())
    if not data:
        return

    hazards = []
    for key, info in data.items():
        parts = key.split(':')
        layer = int(parts[0])
        x, y = map(int, parts[1].split(','))
        hazards.append({
            'x': x, 'y': y,
            'effect': info.get('effect', 'unknown'),
            'confirmed': info.get('confirmed', False),
            'hpHits': info.get('hpHits', 0),
            'mpHits': info.get('mpHits', 0),
            'layer': layer,
        })

    with open(out_file, 'w') as f:
        json.dump({'hazards': hazards, 'count': len(hazards)}, f, indent=2)
    print(f"Hazards: {len(hazards)} entries -> {out_file}")


def convert_items(lua_file, out_file):
    with open(lua_file) as f:
        data = parse_lua_table(f.read())
    if not data:
        return

    items = {}
    for item_id, info in data.items():
        items[str(item_id)] = {
            'name': info.get('name', '?'),
            'cat': info.get('cat', ''),
            'slot': info.get('slot', 0),
            'iLv': info.get('iLv', 0),
            'eLv': info.get('eLv', 0),
            'price': info.get('price', 0),
            'stat': info.get('stat', 0),
        }

    with open(out_file, 'w') as f:
        json.dump(items, f, indent=2)
    print(f"Items: {len(items)} entries -> {out_file}")


def convert_drops(lua_file, items_file, out_file):
    with open(lua_file) as f:
        data = parse_lua_table(f.read())
    if not data:
        return

    # Load item names for resolution
    try:
        with open(items_file) as f:
            items = json.load(f)
    except Exception:
        items = {}

    drops = {}
    for mob_id, info in data.items():
        kills = info.get('kills', 0)
        drop_list = []
        for item_id, count in sorted(info.get('drops', {}).items(), key=lambda x: -x[1]):
            item_name = items.get(str(item_id), {}).get('name', f'item#{item_id}')
            drop_list.append({
                'itemId': item_id,
                'name': item_name,
                'count': count,
                'rate': round(count / kills * 100, 1) if kills > 0 else 0,
            })
        drops[str(mob_id)] = {'kills': kills, 'drops': drop_list}

    with open(out_file, 'w') as f:
        json.dump(drops, f, indent=2)
    print(f"Drops: {len(drops)} monster types -> {out_file}")


def convert_spells(lua_file, out_file):
    with open(lua_file) as f:
        data = parse_lua_table(f.read())
    if not data:
        return

    spells = {}
    for spell_id, info in data.items():
        spells[str(spell_id)] = {
            'name': info.get('name', '?'),
            'manaCostPct': info.get('manaCostPct', 0),
            'measuredCooldownMs': info.get('measuredCooldownMs', 0),
            'minCooldownMs': info.get('minCooldownMs', 0),
            'castCount': info.get('castCount', 0),
        }

    with open(out_file, 'w') as f:
        json.dump(spells, f, indent=2)
    print(f"Spells: {len(spells)} entries -> {out_file}")


def convert_materials(lua_file, out_file):
    with open(lua_file) as f:
        data = parse_lua_table(f.read())
    if not data:
        return

    spawns = []
    for key, info in data.items():
        parts = key.split(':')
        layer = int(parts[0])
        x, y = map(int, parts[1].split(','))
        items_at = info.get('items', {})
        for item_id, item_info in items_at.items():
            spawns.append({
                'x': x, 'y': y,
                'itemId': item_id,
                'name': item_info.get('name', '?'),
                'count': item_info.get('count', 1),
                'layer': layer,
            })

    with open(out_file, 'w') as f:
        json.dump({'spawns': spawns, 'count': len(spawns)}, f, indent=2)
    print(f"Materials: {len(spawns)} spawn entries -> {out_file}")


if __name__ == '__main__':
    out_dir = '.'
    convert_items('discovery_item_database.lua', f'{out_dir}/items.json')
    convert_teleports('discovery_teleport_data.lua', f'{out_dir}/discovered_teleports.json')
    convert_hazards('discovery_hazard_data.lua', f'{out_dir}/discovered_hazards.json')
    convert_drops('discovery_drop_data.lua', f'{out_dir}/items.json', f'{out_dir}/drops.json')
    convert_spells('discovery_spell_data.lua', f'{out_dir}/spells.json')
    if os.path.exists('discovery_material_spawns.lua'):
        convert_materials('discovery_material_spawns.lua', f'{out_dir}/material_spawns.json')
    print("\nDone!")
