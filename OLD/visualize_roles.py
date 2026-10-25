"""Visualizes the organizational roles found by step 5 (organizational_roles.py).

Reads output/organizational_roles.csv and renders:
  - roles_overview.png: bar chart of total events per role, annotated with
    the number of activities/resources in that role.
  - role_activity_network.png: bipartite network of roles <-> activities
    (which activities are grouped into the same role). Resources are not
    drawn as nodes -- some roles have 100+ resources, which would just be
    visual noise; their count is shown as a role-node label instead.

    python visualize_roles.py
    python visualize_roles.py --input output/organizational_roles.csv
"""
import argparse
from pathlib import Path

import networkx as nx
import pandas as pd


def load_roles(csv_path):
    df = pd.read_csv(csv_path)
    df["activity_list"] = df["activities"].apply(lambda s: [a.strip() for a in s.split(";")])
    return df.sort_values("total_events", ascending=False).reset_index(drop=True)


def plot_overview(df, output_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, max(4, 0.35 * len(df))))
    y = range(len(df))
    ax.barh(y, df["total_events"], color="#a7c7e7")
    ax.set_yticks(list(y))
    ax.set_yticklabels([f"role {rid}" for rid in df["role_id"]])
    ax.invert_yaxis()
    ax.set_xlabel("total events")
    ax.set_title("Organizational roles by event volume")

    for i, row in df.iterrows():
        ax.text(row["total_events"], i, f"  {row['num_activities']} act, {row['num_resources']} res",
                va="center", fontsize=7)

    plt.tight_layout()
    out_path = output_dir / "roles_overview.png"
    plt.savefig(out_path, bbox_inches="tight")
    plt.close()
    print(f"Saved '{out_path}'")


def plot_activity_network(df, output_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    graph = nx.Graph()
    role_nodes = []
    activity_nodes = []

    for _, row in df.iterrows():
        role_node = f"role {row['role_id']}"
        role_nodes.append(role_node)
        graph.add_node(role_node, kind="role", num_resources=row["num_resources"])
        for activity in row["activity_list"]:
            if activity not in graph:
                activity_nodes.append(activity)
                graph.add_node(activity, kind="activity")
            graph.add_edge(role_node, activity)

    pos = nx.spring_layout(graph, seed=42, k=0.6)

    plt.figure(figsize=(14, 14))
    role_sizes = [200 + 15 * graph.nodes[n]["num_resources"] for n in role_nodes]
    nx.draw_networkx_nodes(graph, pos, nodelist=role_nodes, node_color="#f4a261",
                            node_size=role_sizes, label="role")
    nx.draw_networkx_nodes(graph, pos, nodelist=activity_nodes, node_color="#a7c7e7",
                            node_size=300, label="activity")
    nx.draw_networkx_edges(graph, pos, alpha=0.4)
    nx.draw_networkx_labels(graph, pos, font_size=7)
    plt.title("Roles <-> activities (role node size ~ number of resources)")
    plt.axis("off")
    plt.legend(scatterpoints=1)

    plt.tight_layout()
    out_path = output_dir / "role_activity_network.png"
    plt.savefig(out_path, bbox_inches="tight")
    plt.close()
    print(f"Saved '{out_path}'")


def main():
    parser = argparse.ArgumentParser(description="Visualize organizational roles discovered by step 5.")
    parser.add_argument("--input", default="output/organizational_roles.csv")
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = load_roles(args.input)
    plot_overview(df, output_dir)
    plot_activity_network(df, output_dir)


if __name__ == "__main__":
    main()
