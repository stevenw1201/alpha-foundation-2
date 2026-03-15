"""
Business Diagram Generator (Graphviz)
Renders value chain, supply chain, and pipeline diagrams for equity research.

Replaces mermaid_render.py — no browser dependency, superior auto-layout,
works for any company topology.

Usage:
    # From a JSON definition (agent generates this)
    python tools/diagram.py --input data/AAPL_value_chain.json --output output/charts/AAPL_value_chain.png

    # From a markdown file (extract and replace ```diagram blocks)
    python tools/diagram.py --markdown output/AAPL_initiation.md --output-dir output/charts/

JSON schema:
{
    "title": "Company Name — Value Chain",
    "direction": "TB",          // TB (top-bottom), LR (left-right)
    "nodes": [
        {"id": "A", "label": "Parent Co", "group": "core"},
        {"id": "B", "label": "Segment 1", "group": "segment"},
        {"id": "C", "label": "Product X", "group": "product"},
        {"id": "D", "label": "Revenue $1B", "group": "metric"}
    ],
    "edges": [
        {"from": "A", "to": "B"},
        {"from": "B", "to": "C", "label": "40% rev"}
    ]
}

Group colors (auto-assigned):
    core      — dark blue (#1B4F72)    — parent company, holding entity
    segment   — medium blue (#2E86C1)  — business segments, subsidiaries
    product   — teal (#17A589)         — products, services, assets
    stage     — amber (#D4AC0D)        — clinical stages, milestones, phases
    outcome   — slate (#5D6D7E)        — outcomes, decisions, endpoints
    metric    — green (#1E8449)        — financial metrics, KPIs
    risk      — red (#C0392B)          — risks, headwinds
    default   — light blue (#85C1E9)   — anything else
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import graphviz
except ImportError:
    print("ERROR: graphviz not installed. Run: pip install graphviz --break-system-packages")
    print("Also need system graphviz: apt-get install graphviz")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Style Config
# ---------------------------------------------------------------------------

GROUP_STYLES = {
    "core": {
        "fillcolor": "#1B4F72",
        "fontcolor": "white",
        "fontsize": "13",
        "style": "filled,bold",
        "shape": "box",
        "penwidth": "2",
    },
    "segment": {
        "fillcolor": "#2E86C1",
        "fontcolor": "white",
        "fontsize": "11",
        "style": "filled",
        "shape": "box",
        "penwidth": "1.5",
    },
    "product": {
        "fillcolor": "#D5F5E3",
        "fontcolor": "#145A32",
        "fontsize": "10",
        "style": "filled",
        "shape": "box",
        "penwidth": "1",
    },
    "stage": {
        "fillcolor": "#FEF9E7",
        "fontcolor": "#7D6608",
        "fontsize": "10",
        "style": "filled",
        "shape": "box",
        "penwidth": "1",
    },
    "outcome": {
        "fillcolor": "#F2F4F4",
        "fontcolor": "#2C3E50",
        "fontsize": "10",
        "style": "filled",
        "shape": "diamond",
        "penwidth": "1",
    },
    "metric": {
        "fillcolor": "#D4EFDF",
        "fontcolor": "#1E8449",
        "fontsize": "10",
        "style": "filled",
        "shape": "box",
        "penwidth": "1",
    },
    "risk": {
        "fillcolor": "#FADBD8",
        "fontcolor": "#922B21",
        "fontsize": "10",
        "style": "filled",
        "shape": "box",
        "penwidth": "1",
    },
    "default": {
        "fillcolor": "#D6EAF8",
        "fontcolor": "#1B4F72",
        "fontsize": "10",
        "style": "filled",
        "shape": "box",
        "penwidth": "1",
    },
}

GRAPH_DEFAULTS = {
    "graph_attr": {
        "bgcolor": "white",
        "pad": "0.5",
        "nodesep": "0.6",
        "ranksep": "0.8",
        "dpi": "150",
        "fontname": "Helvetica",
    },
    "node_attr": {
        "fontname": "Helvetica",
        "margin": "0.2,0.1",
    },
    "edge_attr": {
        "color": "#7F8C8D",
        "arrowsize": "0.8",
        "fontname": "Helvetica",
        "fontsize": "9",
        "fontcolor": "#555555",
    },
}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_diagram(spec: dict, output_path: str) -> bool:
    """
    Render a diagram from a JSON spec to PNG.
    Returns True on success.
    """
    title = spec.get("title", "")
    direction = spec.get("direction", "TB")
    nodes = spec.get("nodes", [])
    edges = spec.get("edges", [])

    if not nodes:
        print("  ERROR: No nodes in diagram spec")
        return False

    # Create graph
    dot = graphviz.Digraph(
        format="png",
        engine="dot",
        graph_attr={
            **GRAPH_DEFAULTS["graph_attr"],
            "rankdir": direction,
            "label": title,
            "labelloc": "t",
            "fontsize": "16",
            "fontname": "Helvetica Bold",
            "fontcolor": "#1B4F72",
        },
        node_attr=GRAPH_DEFAULTS["node_attr"],
        edge_attr=GRAPH_DEFAULTS["edge_attr"],
    )

    # Add nodes
    for node in nodes:
        node_id = node["id"]
        label = _wrap_label(node.get("label", node_id), max_width=28)
        group = node.get("group", "default")
        style = GROUP_STYLES.get(group, GROUP_STYLES["default"])
        dot.node(node_id, label=label, **style)

    # Add edges
    for edge in edges:
        attrs = {}
        if edge.get("label"):
            attrs["label"] = f"  {edge['label']}  "
        if edge.get("style") == "dashed":
            attrs["style"] = "dashed"
        dot.edge(edge["from"], edge["to"], **attrs)

    # Render
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    # graphviz appends .png, so strip it for the render call
    out_base = output_path.rsplit(".", 1)[0] if "." in output_path else output_path
    try:
        dot.render(out_base, cleanup=True)
        print(f"  Rendered: {output_path}")
        return True
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def _wrap_label(text: str, max_width: int = 28) -> str:
    """Wrap long labels for better node rendering."""
    if len(text) <= max_width:
        return text
    words = text.split()
    lines = []
    current = []
    for word in words:
        current.append(word)
        if len(" ".join(current)) > max_width:
            lines.append(" ".join(current))
            current = []
    if current:
        lines.append(" ".join(current))
    return "\\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown Processing
# ---------------------------------------------------------------------------

def process_markdown(md_path: str, output_dir: str) -> str:
    """
    Extract ```diagram JSON blocks from markdown, render each to PNG,
    and replace with image references.
    
    Also handles legacy ```mermaid blocks by attempting conversion.
    """
    content = Path(md_path).read_text()
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    md_filename = Path(md_path).stem

    # Process ```diagram blocks (new format)
    diagram_pattern = re.compile(r'```diagram\n(.*?)```', re.DOTALL)
    matches = list(diagram_pattern.finditer(content))

    for i, match in enumerate(reversed(matches)):
        json_str = match.group(1).strip()
        try:
            spec = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"  ERROR: Invalid JSON in diagram block {i+1}: {e}")
            continue

        img_filename = f"{md_filename}_diagram_{i+1}.png"
        img_path = str(Path(output_dir) / img_filename)

        print(f"\nRendering diagram block {i+1}...")
        if render_diagram(spec, img_path):
            rel_path = os.path.relpath(img_path, Path(md_path).parent)
            replacement = f"![{spec.get('title', 'Diagram')}]({rel_path})"
            content = content[:match.start()] + replacement + content[match.end():]

    # Process legacy ```mermaid blocks (convert simple cases)
    mermaid_pattern = re.compile(r'```mermaid\n(.*?)```', re.DOTALL)
    mermaid_matches = list(mermaid_pattern.finditer(content))

    for i, match in enumerate(reversed(mermaid_matches)):
        mermaid_code = match.group(1).strip()
        spec = _mermaid_to_spec(mermaid_code)
        if not spec:
            print(f"  WARNING: Could not convert mermaid block {i+1}, keeping as code")
            continue

        img_filename = f"{md_filename}_mermaid_{i+1}.png"
        img_path = str(Path(output_dir) / img_filename)

        print(f"\nRendering mermaid block {i+1} (via graphviz)...")
        if render_diagram(spec, img_path):
            rel_path = os.path.relpath(img_path, Path(md_path).parent)
            replacement = f"![{spec.get('title', 'Diagram')}]({rel_path})"
            content = content[:match.start()] + replacement + content[match.end():]

    Path(md_path).write_text(content)
    print(f"\nUpdated markdown: {md_path}")
    return content


def _mermaid_to_spec(code: str) -> dict | None:
    """Convert simple mermaid graph syntax to our JSON spec."""
    lines = code.strip().split("\n")
    if not lines:
        return None

    header = lines[0].strip()
    direction = "TB"
    if "LR" in header:
        direction = "LR"
    elif "RL" in header:
        direction = "RL"
    elif "BT" in header:
        direction = "BT"

    nodes = {}
    node_shapes = {}
    edges = []

    # Extract node definitions: ID[label], ID{label}, ID(label)
    for bracket_open, bracket_close, shape in [("[", "]", "box"), ("{", "}", "diamond"), ("(", ")", "ellipse")]:
        escaped_open = re.escape(bracket_open)
        escaped_close = re.escape(bracket_close)
        pattern = re.compile(
            r'\b([A-Za-z]\w*)\s*' + escaped_open +
            r'([^' + escaped_close + r']+)' + escaped_close
        )
        for match in pattern.finditer(code):
            nid = match.group(1)
            if nid.lower() in ("graph", "subgraph", "end", "style", "class", "click", "linkstyle"):
                continue
            nodes[nid] = match.group(2).strip()
            node_shapes[nid] = shape

    # Extract edges
    edge_pattern = re.compile(
        r'\b([A-Za-z]\w*)\s*'
        r'(?:\[[^\]]*\]|\{[^\}]*\}|\([^\)]*\))?\s*'
        r'(?:--+>|==+>|-.+->|--+)'
        r'\s*(?:\|([^|]*)\|)?\s*'
        r'([A-Za-z]\w*)'
    )
    for line in lines[1:]:
        line = line.strip()
        if not line or line.startswith('%%'):
            continue
        for match in edge_pattern.finditer(line):
            src, label, dst = match.group(1), match.group(2) or "", match.group(3)
            if src.lower() in ("graph", "subgraph", "end") or dst.lower() in ("graph", "subgraph", "end"):
                continue
            edges.append({"from": src, "to": dst, "label": label.strip()})
            if src not in nodes:
                nodes[src] = src
            if dst not in nodes:
                nodes[dst] = dst

    if not nodes:
        return None

    # Auto-assign groups based on depth (BFS from roots)
    children_map = {}
    parent_set = set()
    for e in edges:
        children_map.setdefault(e["from"], []).append(e["to"])
        parent_set.add(e["to"])
    roots = [n for n in nodes if n not in parent_set]
    if not roots:
        roots = [list(nodes.keys())[0]]

    depth = {}
    queue = [(r, 0) for r in roots]
    visited = set(roots)
    while queue:
        nid, d = queue.pop(0)
        depth[nid] = d
        for child in children_map.get(nid, []):
            if child not in visited:
                visited.add(child)
                queue.append((child, d + 1))
    for n in nodes:
        if n not in depth:
            depth[n] = max(depth.values()) + 1 if depth else 0

    max_depth = max(depth.values()) if depth else 0
    depth_groups = {
        0: "core",
        1: "segment",
        2: "product",
    }

    node_list = []
    for nid, label in nodes.items():
        d = depth.get(nid, 0)
        if node_shapes.get(nid) == "diamond":
            group = "outcome"
        elif d in depth_groups:
            group = depth_groups[d]
        elif d == max_depth:
            group = "metric"
        else:
            group = "stage"
        node_list.append({"id": nid, "label": label, "group": group})

    return {
        "title": "",
        "direction": direction,
        "nodes": node_list,
        "edges": edges,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Business Diagram Generator (Graphviz)")
    parser.add_argument("--input", default=None, help="Input JSON diagram spec")
    parser.add_argument("--output", default=None, help="Output PNG path")
    parser.add_argument("--markdown", default=None,
                        help="Markdown file — extract, render, and replace diagram/mermaid blocks")
    parser.add_argument("--output-dir", default="output/charts",
                        help="Output directory for rendered PNGs (for --markdown)")

    args = parser.parse_args()

    if args.markdown:
        process_markdown(args.markdown, args.output_dir)

    elif args.input:
        spec = json.loads(Path(args.input).read_text())
        output = args.output or args.input.replace(".json", ".png")
        render_diagram(spec, output)

    else:
        print("ERROR: Provide --input or --markdown")
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
