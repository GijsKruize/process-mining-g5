Reference results for checking a run on your own machine.

Command (from the repository root):

    python main.py "data/BPI2017Denied(3).xes" --attribute org:resource

Files here come from that command on a 2-core Linux machine, Python 3.9.25,
with the packages pinned in requirements.txt:

    pattern_stats.csv          should match output/pattern_stats.csv
    instance_graph_stats.json  same model size and BIG counts (times will differ)
    roles.csv                  should match output/roles.csv
    attribute_groups.csv       should match output/attribute_groups.csv
    instance_graphs.g.md5      MD5 of output/instance_graphs.g

Two runs on the same machine are byte-identical. Across operating systems
this has not been verified; if the MD5 differs but pattern_stats.csv matches,
only the choice among equally good alignments differs.
