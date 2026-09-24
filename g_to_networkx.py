"""Standalone utility: convert BIG-format .g files to networkx graphs.

Wraps instance_graphs.py's InstanceGraphParser (already tested against both
the real BPI2017Denied.g example and this project's own generated output) as
a general-purpose CLI, independent of the rest of the step 2 pipeline. Useful
for converting any .g file -- one you generated elsewhere, an old run's
output, a course-provided example -- without needing a relabelled log,
a Petri net, or BIG itself.

Each input .g file is parsed into a list of networkx.DiGraph objects (one per
'XP'/'XN' graph in the file, globally unique node ids across that file) and
pickled next to a summary printed to stdout.

Usage:
    python g_to_networkx.py FILE_OR_DIR [FILE_OR_DIR ...] [-o OUTPUT] [--combine]

Examples:
    # Convert one file -> BPI2017Denied.pkl next to it
    python g_to_networkx.py datasets_group5_mining_organizational_patterns/BPI2017Denied.g

    # Convert every .g file in a directory, one .pkl per file
    python g_to_networkx.py output/

    # Convert several files into a single combined pickle
    python g_to_networkx.py a.g b.g c.g -o combined.pkl --combine
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path
from typing import List, Optional

import networkx as nx

from instance_graphs import InstanceGraphParser


def collect_g_files(paths: List[str]) -> List[Path]:
    """Expand a mix of file and directory arguments into a sorted list of .g files."""
    g_files: List[Path] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            found = sorted(path.glob("*.g"))
            if not found:
                print(f"Warning: no .g files found in directory '{path}'", file=sys.stderr)
            g_files.extend(found)
        elif path.is_file():
            g_files.append(path)
        else:
            raise FileNotFoundError(f"No such file or directory: '{path}'")
    return g_files


def convert_file(path: Path, parser: InstanceGraphParser) -> List[nx.DiGraph]:
    """Parse one .g file and print a one-line summary."""
    graphs = parser.parse(path)
    stats = parser.summarize(graphs)
    print(
        f"{path}: {stats['n_graphs']} graph(s), {stats['n_nodes']} node(s), "
        f"{stats['n_edges']} edge(s)"
    )
    return graphs


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert BIG-format .g files to networkx.DiGraph objects, pickled for reuse."
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="One or more .g files and/or directories (all *.g files in each are converted).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output pickle path. With --combine, all inputs are merged into this one file "
        "(required in that case). Without --combine, only valid for a single input file "
        "(default: that file with its extension replaced by .pkl).",
    )
    parser.add_argument(
        "--combine",
        action="store_true",
        help="Merge all input files' graphs into a single output pickle (requires -o).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)

    try:
        g_files = collect_g_files(args.paths)
        if not g_files:
            raise FileNotFoundError("No .g files found among the given paths.")

        if args.combine and not args.output:
            raise ValueError("--combine requires -o/--output to name the merged output file.")
        if args.output and not args.combine and len(g_files) > 1:
            raise ValueError(
                "-o/--output with multiple input files requires --combine "
                "(otherwise every file would overwrite the same output)."
            )

        parser = InstanceGraphParser()

        if args.combine:
            combined: List[nx.DiGraph] = []
            for g_file in g_files:
                combined.extend(convert_file(g_file, parser))
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as pickle_file:
                pickle.dump(combined, pickle_file)
            print(f"Combined {len(g_files)} file(s) into '{output_path}' ({len(combined)} graphs)")
        else:
            for g_file in g_files:
                graphs = convert_file(g_file, parser)
                output_path = Path(args.output) if args.output else g_file.with_suffix(".pkl")
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as pickle_file:
                    pickle.dump(graphs, pickle_file)
                print(f"  -> saved to '{output_path}'")
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
