"""Shared artifact IO and streaming XES reader; no discovery or mining side effects."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
from lxml import etree
from . import config

STEP1 = config.STEP1_OUTPUT_DIR / 'org_resource_roles'
STEP2 = config.STEP2_OUTPUT_DIR / 'org_resource_roles'
GRAPHS = STEP2 / 'instance_graphs.pkl'
LOG = STEP1 / 'relabeled_log.xes'
NET = STEP2 / 'petri_net.pnml'


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def write_csv(path, rows, fields=None):
    rows = list(rows)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def iter_traces(path):
    """Yield (case id, event attribute dicts) in stored order; timestamps stay strings."""
    path = Path(path)
    with (gzip.open(path, 'rb') if path.suffix == '.gz' else path.open('rb')) as stream:
        for _, elem in etree.iterparse(stream, events=('end',), tag='{*}trace'):
            case, events = None, []
            for child in elem:
                if etree.QName(child).localname == 'event':
                    events.append({a.get('key'): a.get('value') for a in child if a.get('key') is not None})
                elif child.get('key') == 'concept:name':
                    case = child.get('value')
            yield case, events
            elem.clear()
            while elem.getprevious() is not None:
                del elem.getparent()[0]
