#!/usr/bin/env python3
"""Validate *roadmap data files*, not the UI4ME application. Safe optional static check."""
import json
from pathlib import Path
r=Path(__file__).parent
items=json.loads((r/'data/WORK_ITEMS.json').read_text())['items']
ids=[x['id'] for x in items]
assert len(ids)==len(set(ids)), 'duplicate roadmap item id'
versions=set(json.loads((r/'data/WORK_ITEMS.json').read_text())['versions'])
assert set(x['version'] for x in items)<=versions
orig=json.loads((r/'data/ORIGINAL_INVENTORY_RECONCILED.json').read_text())['records']
assert len(orig)==224 and len({x['id'] for x in orig})==224
print(f"Roadmap data coherent: {len(items)} work items; {len(orig)} source inventory features")
