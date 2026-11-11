#!/usr/bin/env python3
"""Validate the planning catalogue and optionally revalidate original zip code anchors.
No external dependencies, no tests or build of UI4ME.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1]

def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1<<20),b''):h.update(block)
 return h.hexdigest()

def run(archive:Path|None):
 doc=json.loads((ROOT/'data/features.json').read_text())
 rs=json.loads((ROOT/'data/old-source-references.json').read_text())
 summary=json.loads((ROOT/'data/catalog-summary.json').read_text())
 features=doc['features'];refs=rs['references']
 byid={f['id']:f for f in features}
 assert len(byid)==len(features), 'Duplicate feature ID'
 assert len(features)==summary['feature_count']
 assert len(refs)==summary['old_source_reference_count']
 assert len([f for f in features if f['old_refs']])==summary['old_anchored_features']
 assert all(r['feature_id'] in byid for r in refs)
 assert all(f['old_evidence']=='none' or f['old_refs'] for f in features)
 assert all(dep in byid for f in features for dep in f['depends_on'])
 for f in features:
  assert f['layer'] in ('Core','Optional UI','Extension','Application','Delivery')
  assert f['title'] and f['rationale'] and f['acceptance']
  if f['layer'] in ('Optional UI','Extension','Application'):
   assert not f['old_refs'], f"Unexpected direct old Core source claim for {f['id']}"
 for r in refs:
  assert r['source_snapshot_sha256']==rs['archive_sha256']
  assert r['path'].startswith(('engine/','bindings/','tools/'))
  assert r['line_start']<=r['match_line']<=r['line_end']
  assert '../' not in r['path']
 if archive:
  assert sha(archive)==rs['archive_sha256'],'Original zip differs: source line refs NOT valid'
  with ZipFile(archive) as z:
   for r in refs:
    name='ui4me-main/'+r['path']
    text=z.read(name).decode('utf-8',errors='replace').splitlines()
    assert 1<=r['line_start']<=r['match_line']<=r['line_end']<=len(text),(r,name)
    assert text[r['match_line']-1].strip()[:220]==r['match_text'],(name,r['match_line'])
  print('Old ZIP SHA-256 and all',len(refs),'source match lines verified')
 else:
  print('No old zip provided: exact archived code lines NOT rechecked')
 # Validate package manifest when present (manifest does not hash itself)
 manifest=ROOT/'data/SOURCE_MANIFEST.json'
 if manifest.exists():
  data=json.loads(manifest.read_text())
  for item in data['files']:
   p=ROOT/item['path']
   assert p.is_file() and sha(p)==item['sha256'],f"Package drift: {p}"
  print('Package file hashes validated:',len(data['files']))
 print('OK:',len(features),'features;',len(refs),'old-source references; 5 architectural layers')

if __name__=='__main__':
 parser=argparse.ArgumentParser()
 parser.add_argument('--old-zip',type=Path,help='Optional exact original bigbatmanorg-ui4me-old.zip for validating line anchors')
 a=parser.parse_args();run(a.old_zip)
