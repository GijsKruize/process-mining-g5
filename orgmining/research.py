"""Research-stage orchestration; preserve and fingerprint existing baseline artifacts."""
import json
from pathlib import Path
from .artifacts import GRAPHS, LOG, NET, sha256, write_json


def run():
    from .conformance import run as conformance
    from .patterns import run as mine
    from .exports import run as export
    from .evaluation import run as evaluate
    from .reporting import run as report
    paths=[LOG,NET,GRAPHS,GRAPHS.with_suffix('.g'),GRAPHS.parent/'summary.json']
    before={str(p):sha256(p) for p in paths}
    write_json('outputs/paper/baseline_manifest.json',before)
    conformance()
    for folder,action in [('outputs/step3_patterns',mine),('outputs/instance_graph_exports',export)]:
        path=Path(folder)/'summary.json'
        if path.exists():
            info=json.loads(path.read_text())
            if info['input_sha256']!=before[str(GRAPHS)]:
                raise ValueError(f'{folder} belongs to a different baseline')
        else:
            action()
    if not Path("outputs/conformance/selected_cases/summary.json").exists():
        from .repair_diagnostics import run as inspect
        inspect()
    evaluate()
    if {str(p):sha256(p) for p in paths}!=before:
        raise RuntimeError('A baseline input changed during the research run')
    report()
