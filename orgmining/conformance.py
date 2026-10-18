"""Full-log exact alignments against the saved model, cached by label sequence.

Use the same PM4Py state-equation A* engine as BIG. Cache the empty-trace
best-worst cost once per process rather than recomputing it for each case.
Fitness follows PM4Py 2.2.16's integer-cost normalization, including silent costs.
A separate move-based fitting flag ignores permitted silent model moves.
"""
import json
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np
from .artifacts import LOG, NET, iter_traces, sha256, write_csv, write_json

_NET = None


def _initialize(net_path, timeout):
    global _NET, _IM, _FM, _BWC, _TIMEOUT
    from pm4py.objects.petri_net.importer import importer
    from pm4py.algo.conformance.alignments.petri_net.variants import state_equation_a_star as astar
    _NET, _IM, _FM = importer.apply(net_path)
    _BWC = astar.get_best_worst_cost(_NET, _IM, _FM)
    _TIMEOUT = timeout


def _align(task):
    from pm4py.objects.log.obj import Trace, Event
    from pm4py.algo.conformance.alignments.petri_net.variants import state_equation_a_star as astar
    key, labels = task
    started = time.time()
    trace = Trace([Event({'concept:name': label}) for label in labels])
    result = astar.apply(trace, _NET, _IM, _FM, parameters={
        'trace_cost_function': [10000] * len(trace), 'max_align_time_trace': _TIMEOUT})
    if result is None:
        return dict(variant_id=key, status='timeout', seconds=time.time()-started)
    moves = result['alignment']
    bwc = len(trace)*10000 + _BWC
    return dict(variant_id=key, status='ok',
                fitness=1-(result['cost']//10000)/(bwc//10000) if bwc>0 else 0,
                cost=int(result['cost']), bwc=int(bwc),
                synchronous_moves=sum(a==b and a!='>>' for a,b in moves),
                log_moves=sum(a!='>>' and b=='>>' for a,b in moves),
                visible_model_moves=sum(a=='>>' and b not in (None,'>>') for a,b in moves),
                silent_model_moves=sum(a=='>>' and b is None for a,b in moves),
                seconds=round(time.time()-started,4))


def run(log_path=LOG, net_path=NET, output='outputs/conformance', workers=3, timeout=600):
    import pm4py
    if pm4py.__version__ != '2.2.16':
        raise RuntimeError('This assignment requires pm4py 2.2.16')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    fingerprint = dict(log_sha256=sha256(log_path), net_sha256=sha256(net_path),
                       pm4py_version=pm4py.__version__, algorithm='state_equation_a_star',
                       cost_scheme='PM4Py default; visible=10000, silent=1; fitness floor normalization')
    manifest = output / 'inputs.json'
    if manifest.exists() and json.loads(manifest.read_text()) != fingerprint:
        raise ValueError('Cached inputs differ; choose another output folder.')
    write_json(manifest, fingerprint)
    variants, cases = {}, []
    for index, (case, events) in enumerate(iter_traces(log_path)):
        labels = tuple(e['concept:name'] for e in events)
        variants.setdefault(labels, len(variants))
        cases.append(dict(graph_index=index, case_id=case, events=len(events), variant_id=variants[labels]))
    cache_path = output / 'alignment_cache.jsonl'
    cache = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            row = json.loads(line)
            if row['status'] == 'ok':
                cache[row['variant_id']] = row
    tasks = [(key, labels) for labels, key in variants.items() if key not in cache]
    print(f'{len(cases)} cases, {len(variants)} variants; {len(cache)} cached, {len(tasks)} to align', flush=True)
    started = time.time()
    with cache_path.open('a', encoding='utf-8', buffering=1) as stream:
        with ProcessPoolExecutor(max_workers=workers, initializer=_initialize,
                                 initargs=(str(Path(net_path).resolve()), timeout)) as pool:
            futures = [pool.submit(_align, task) for task in tasks]
            for n, future in enumerate(as_completed(futures), 1):
                row = future.result()
                cache[row['variant_id']] = row
                stream.write(json.dumps(row)+'\n')
                if n % 25 == 0 or n == len(tasks):
                    print(f'Aligned {n}/{len(tasks)} variants; {time.time()-started:.0f}s', flush=True)
    rows=[]
    for case in cases:
        row = {**case, **cache[case['variant_id']]}
        row['requires_visible_repair'] = (row.get('log_moves',0)+row.get('visible_model_moves',0)>0) if row['status']=='ok' else ''
        rows.append(row)
    fields = list(dict.fromkeys(k for r in rows for k in r))
    write_csv(output/'per_case.csv', rows, fields)
    ok = [r for r in rows if r['status']=='ok']
    stats = dict(cases_total=len(rows), cases_completed=len(ok), cases_incomplete=len(rows)-len(ok),
                 unique_variants=len(variants), workers=workers, timeout_seconds=timeout,
                 fitting_cases=sum(not r['requires_visible_repair'] for r in ok),
                 cases_requiring_visible_repair=sum(r['requires_visible_repair'] for r in ok),
                 event_rows=sum(r['events'] for r in rows),
                 average_trace_fitness=float(np.mean([r['fitness'] for r in ok])) if ok else None,
                 log_fitness=1-sum(r['cost'] for r in ok)/sum(r['bwc'] for r in ok) if ok else None,
                 visible_cost_log_fitness=1-sum(r['cost']//10000 for r in ok)/sum(r['bwc']//10000 for r in ok) if ok else None,
                 fitness_quantiles={str(q):float(np.quantile([r['fitness'] for r in ok],q)) for q in [0,.25,.5,.75,1]} if ok else {},
                 totals={k:sum(r[k] for r in ok) for k in ['synchronous_moves','log_moves','visible_model_moves','silent_model_moves']},
                 elapsed_seconds_this_run=round(time.time()-started,2),
                 note='Recomputed alignments of the saved model; optimal tie breaks can differ from historical BIG alignments. Fitness is in-sample, not held-out validation.')
    stats['fitting_cases_pct']=100*stats['fitting_cases']/len(rows)
    previous_path=output/'summary.json'
    previous=json.loads(previous_path.read_text()) if previous_path.exists() else {}
    stats['first_full_run_wall_seconds']=previous.get('first_full_run_wall_seconds', stats['elapsed_seconds_this_run'])
    stats['alignment_worker_seconds']=sum(row.get('seconds',0) for row in cache.values())
    write_json(output/'summary.json',stats)
    write_csv(output/'worst_cases.csv',sorted(ok,key=lambda r:r['fitness'])[:30],fields)
    print(json.dumps(stats,indent=2),flush=True)
    return stats
