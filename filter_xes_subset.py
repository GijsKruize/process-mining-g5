"""Create a smaller XES subset by filtering complete traces.

This script intentionally does not use pm4py. It streams the XML trace by
trace, which makes it suitable for creating small test logs from the BPI 2017
Denied file without loading the whole dataset into memory first.
"""
import argparse
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET

from xml.sax.saxutils import quoteattr


def resolve_input_path(path):
    """Resolve tiny pointer files like data/BPI2017Denied(3).xes."""
    path = Path(path)
    if path.is_file() and path.stat().st_size < 512:
        content = path.read_text(encoding="utf-8").strip()
        candidate = (path.parent / content).resolve()
        if candidate.is_file():
            return candidate
    return path


def xes_key(attribute):
    """pm4py exposes trace attributes as case:X; raw XES stores them as X."""
    return attribute.removeprefix("case:")


def format_start_tag(element):
    attrs = " ".join(
        f"{key}={quoteattr(value)}"
        for key, value in element.attrib.items()
    )
    return f"<{element.tag}{(' ' + attrs) if attrs else ''}>"


def trace_attribute_value(trace, attribute):
    for child in trace:
        if child.tag == "event":
            return None
        if child.attrib.get("key") == attribute:
            return child.attrib.get("value")
    return None


def iter_root_children(path):
    """Yield root-level child elements from a XES file."""
    context = ET.iterparse(path, events=("start", "end"))
    root = None
    depth = 0
    for event, element in context:
        if event == "start":
            depth += 1
            if root is None:
                root = element
                yield "root", root
        elif event == "end":
            if depth == 2:
                yield "child", element
                element.clear()
                if root is not None:
                    root.clear()
            depth -= 1


def list_values(input_path, attribute):
    counts = Counter()
    total = 0
    for kind, element in iter_root_children(input_path):
        if kind == "child" and element.tag == "trace":
            total += 1
            value = trace_attribute_value(element, attribute) or "UNKNOWN"
            counts[value] += 1
    return total, counts


def write_subset(input_path, output_path, attribute, value, max_traces=None):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    seen = 0
    kept = 0
    with output_path.open("w", encoding="utf-8", newline="\n") as out:
        out.write('<?xml version="1.0" encoding="UTF-8" ?>\n')
        for kind, element in iter_root_children(input_path):
            if kind == "root":
                out.write(format_start_tag(element))
                out.write("\n")
            elif kind == "child" and element.tag == "trace":
                seen += 1
                if trace_attribute_value(element, attribute) == value:
                    if max_traces is None or kept < max_traces:
                        out.write(ET.tostring(element, encoding="unicode"))
                        out.write("\n")
                        kept += 1
            elif kind == "child":
                out.write(ET.tostring(element, encoding="unicode"))
                out.write("\n")
        out.write("</log>\n")
    return seen, kept


def main():
    parser = argparse.ArgumentParser(description="Filter a XES log to a smaller trace subset.")
    parser.add_argument("input_path", help="Input XES path, or a pointer file containing the real path")
    parser.add_argument("--attribute", default="LoanGoal",
                        help="Trace attribute to filter on, e.g. LoanGoal or case:LoanGoal")
    parser.add_argument("--value", default="Car", help="Trace attribute value to keep")
    parser.add_argument("--output", default=None, help="Output XES path")
    parser.add_argument("--max-traces", type=int, default=None,
                        help="Optional cap for an even smaller test subset")
    parser.add_argument("--list-values", action="store_true",
                        help="Only print value counts for the selected trace attribute")
    args = parser.parse_args()

    input_path = resolve_input_path(args.input_path)
    attribute = xes_key(args.attribute)

    if args.list_values:
        total, counts = list_values(input_path, attribute)
        print(f"{total} traces in {input_path}")
        for value, count in counts.most_common():
            print(f"{value}: {count}")
        return

    output = args.output
    if output is None:
        safe_value = "".join(ch if ch.isalnum() else "_" for ch in args.value).strip("_")
        output = Path("data") / f"BPI2017Denied_{attribute}_{safe_value}.xes"

    seen, kept = write_subset(input_path, output, attribute, args.value, args.max_traces)
    print(f"Input:  {input_path}")
    print(f"Output: {output}")
    print(f"Kept {kept} of {seen} traces where {attribute} == {args.value!r}")


if __name__ == "__main__":
    main()
