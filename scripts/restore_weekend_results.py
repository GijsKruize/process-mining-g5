"""Restore committed derived outputs without committing the input event log."""
import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run(unpack=False,overwrite=False):
    saved=ROOT/'results/weekend'
    manifest=json.loads((saved/'manifest.json').read_text(encoding='utf-8'))
    for record in manifest['files']:
        relative=Path(record['path'])
        source=saved/relative
        target=ROOT/'outputs'/relative
        if target.exists() and not overwrite:
            continue
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target)
    if unpack:
        archive=ROOT/'outputs/instance_graph_exports/all_instance_graphs.zip'
        target=archive.parent.resolve()
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                destination=(target/info.filename).resolve()
                if not destination.is_relative_to(target):
                    raise ValueError('Archive entry falls outside the graph folder')
                if destination.exists() and not overwrite:
                    continue
                bundle.extract(info,target)
    pickle=ROOT/'outputs/step2_instance_graphs/org_resource_roles/instance_graphs.pkl'
    if not pickle.exists() or overwrite:
        import pandas as pd
        from orgmining.graph_io import GFileConverter
        step2=pickle.parent
        table=pd.read_csv(step2/'instance_graphs_summary.csv')
        converter=GFileConverter.from_label_counts(ROOT/'outputs/step1_preprocessing/org_resource_roles/label_counts.csv')
        graphs=converter.convert(step2/'instance_graphs.g',list(table.case_id))
        converter.save(graphs,pickle)
    print('Derived results restored; existing files preserved unless --overwrite was selected.')
    print('The original and relabelled XES inputs are not included; use the Canvas dataset for preprocessing/conformance reruns.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unpack-graphs',action='store_true')
    parser.add_argument('--overwrite',action='store_true')
    args=parser.parse_args()
    run(args.unpack_graphs,args.overwrite)
