"""Cost-versus-accuracy scatter. Local only; the Modal image does not import this."""

from __future__ import annotations

import math
import re
from pathlib import Path

_FONTSIZE = 9
_LABEL_GAP = 8
_COLORS = (
    "#1f4b99",
    "#d35400",
    "#1e8449",
    "#6c3483",
    "#b03a2e",
    "#117a65",
    "#b7950b",
    "#1a5276",
)


def display_label(label: object) -> str:
    """Point text. The keyword arm is never titled BM25."""
    text = str(label).strip()
    if re.search(r"\bbm25\b", text, flags=re.IGNORECASE):
        return "keyword search"
    return text


def _center_offsets(index: int, width_px: float, height_px: float, px_per_pt: float) -> list[tuple[float, float]]:
    """Candidate label-center offsets in points, nearest ring first."""
    half_w = width_px / 2 / px_per_pt
    half_h = height_px / 2 / px_per_pt
    offsets: list[tuple[float, float]] = []
    for gap in (12, 22, 34, 48, 64, 82):
        angles = list(range(0, 360, 30))
        shift = (index * 3) % len(angles)
        angles = angles[shift:] + angles[:shift]
        for deg in angles:
            rad = math.radians(deg)
            offsets.append((math.cos(rad) * (half_w + gap), math.sin(rad) * (half_h + gap)))
    return offsets


def _padded(box, pad: float):
    from matplotlib.transforms import Bbox

    return Bbox.from_extents(box.x0 - pad, box.y0 - pad, box.x1 + pad, box.y1 + pad)


def _chrome_boxes(ax, renderer) -> list:
    boxes = []
    for artist in (ax.title, ax.xaxis.label, ax.yaxis.label):
        box = artist.get_window_extent(renderer)
        if box.width > 1 and box.height > 1:
            boxes.append(_padded(box, 3))
    for tick in list(ax.get_xticklabels()) + list(ax.get_yticklabels()):
        if not tick.get_visible():
            continue
        box = tick.get_window_extent(renderer)
        if box.width > 1 and box.height > 1:
            boxes.append(_padded(box, 1))
    return boxes


def _marker_boxes(ax, xs, ys) -> list:
    from matplotlib.transforms import Bbox

    px_per_pt = ax.figure.dpi / 72.0
    radius = math.sqrt(90) * px_per_pt / 2 + 4
    boxes = []
    for x, y in zip(xs, ys):
        cx, cy = ax.transData.transform((float(x), float(y)))
        boxes.append(Bbox.from_extents(cx - radius, cy - radius, cx + radius, cy + radius))
    return boxes


def _inside_figure(box, figure, margin: float = 3) -> bool:
    frame = figure.bbox
    return box.x0 >= margin and box.y0 >= margin and box.x1 <= frame.x1 - margin and box.y1 <= frame.y1 - margin


def _overlaps(box, others) -> bool:
    return any(box.overlaps(other) for other in others)


def _predicted_box(anchor, dx_pt: float, dy_pt: float, width_px: float, height_px: float, px_per_pt: float, pad: float):
    from matplotlib.transforms import Bbox

    cx = anchor[0] + dx_pt * px_per_pt
    cy = anchor[1] + dy_pt * px_per_pt
    return Bbox.from_extents(cx - width_px / 2 - pad, cy - height_px / 2 - pad, cx + width_px / 2 + pad, cy + height_px / 2 + pad)


def _annotation_boxes(annotations, renderer):
    """Text boxes only. Leader lines may cross empty space."""
    from matplotlib.text import Text

    boxes = []
    for ann in annotations:
        if renderer is not None:
            ann._renderer = renderer
        ann.update_positions(ann._renderer)
        boxes.append(_padded(Text.get_window_extent(ann), _LABEL_GAP))
    return boxes


def _labels_separated(annotations, renderer, figure) -> bool:
    boxes = _annotation_boxes(annotations, renderer)
    for box in boxes:
        if not _inside_figure(box, figure, margin=1):
            return False
    for index, box in enumerate(boxes):
        if _overlaps(box, boxes[index + 1 :]):
            return False
    return True


def _nudge_apart(annotations, renderer, figure, px_per_pt: float) -> None:
    boxes = _annotation_boxes(annotations, renderer)
    for index, box in enumerate(boxes):
        shift_x = 0.0
        shift_y = 0.0
        frame = figure.bbox
        if box.x0 < 4:
            shift_x += 4 - box.x0
        if box.y0 < 4:
            shift_y += 4 - box.y0
        if box.x1 > frame.x1 - 4:
            shift_x -= box.x1 - (frame.x1 - 4)
        if box.y1 > frame.y1 - 4:
            shift_y -= box.y1 - (frame.y1 - 4)
        for other in boxes[index + 1 :]:
            if not box.overlaps(other):
                continue
            overlap_x = min(box.x1, other.x1) - max(box.x0, other.x0)
            overlap_y = min(box.y1, other.y1) - max(box.y0, other.y0)
            cx = (box.x0 + box.x1) / 2 - (other.x0 + other.x1) / 2
            cy = (box.y0 + box.y1) / 2 - (other.y0 + other.y1) / 2
            if overlap_x <= overlap_y:
                shift_x += math.copysign(overlap_x / 2 + 4, cx if abs(cx) > 0.5 else -1)
            else:
                shift_y += math.copysign(overlap_y / 2 + 4, cy if abs(cy) > 0.5 else 1)
        if abs(shift_x) < 0.5 and abs(shift_y) < 0.5:
            continue
        dx_pt, dy_pt = annotations[index].xyann
        annotations[index].xyann = (dx_pt + shift_x / px_per_pt, dy_pt + shift_y / px_per_pt)


def _legend(ax, labels: list[str], colors: list[str]) -> str:
    from matplotlib.lines import Line2D

    handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="None",
            markerfacecolor=colors[index],
            markeredgecolor="white",
            markersize=8,
            label=label,
        )
        for index, label in enumerate(labels)
    ]
    ax.legend(handles=handles, loc="best", fontsize=8, framealpha=0.94, borderpad=0.6)
    return "legend"


def draw_labeled_scatter(ax, xs: list[float], ys: list[float], labels: list[object]) -> str:
    """Color each arm and keep its name off the other names.

    Returns "labels" when every name is an offset annotation, or "legend" when
    the points are too close for that and the names sit in a legend instead.
    """
    from matplotlib.font_manager import FontProperties

    shown = [display_label(label) for label in labels]
    colors = [_COLORS[index % len(_COLORS)] for index in range(len(shown))]
    if xs:
        ax.scatter(xs, ys, s=90, c=colors, zorder=3, edgecolors="white", linewidths=0.6)
    if not shown:
        return "labels"

    figure = ax.figure
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    px_per_pt = figure.dpi / 72.0
    font = FontProperties(size=_FONTSIZE)
    anchors = [ax.transData.transform((float(x), float(y))) for x, y in zip(xs, ys)]
    obstacles = _chrome_boxes(ax, renderer) + _marker_boxes(ax, xs, ys)
    placed = []
    annotations = []
    for index, label in enumerate(shown):
        width, height, descent = renderer.get_text_width_height_descent(label, font, ismath=False)
        text_h = height + descent
        chosen = None
        for dx_pt, dy_pt in _center_offsets(index, width, text_h, px_per_pt):
            box = _predicted_box(anchors[index], dx_pt, dy_pt, width, text_h, px_per_pt, pad=_LABEL_GAP)
            if not _inside_figure(box, figure):
                continue
            if _overlaps(box, obstacles) or _overlaps(box, placed):
                continue
            chosen = (dx_pt, dy_pt, box)
            break
        if chosen is None:
            for ann in annotations:
                ann.remove()
            return _legend(ax, shown, colors)
        dx_pt, dy_pt, box = chosen
        ann = ax.annotate(
            label,
            (float(xs[index]), float(ys[index])),
            textcoords="offset points",
            xytext=(dx_pt, dy_pt),
            fontsize=_FONTSIZE,
            ha="center",
            va="center",
            color="#17202a",
            annotation_clip=False,
            arrowprops={
                "arrowstyle": "-",
                "color": colors[index],
                "lw": 0.8,
                "shrinkA": 6,
                "shrinkB": 7,
            },
            zorder=4,
        )
        annotations.append(ann)
        placed.append(box)

    for _ in range(10):
        figure.canvas.draw()
        if _labels_separated(annotations, renderer, figure):
            return "labels"
        _nudge_apart(annotations, renderer, figure, px_per_pt)
    figure.canvas.draw()
    if _labels_separated(annotations, renderer, figure):
        return "labels"
    for ann in annotations:
        ann.remove()
    return _legend(ax, shown, colors)


def write_cost_accuracy_plot(arms: list[dict], path: Path, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8.2, 5.1), dpi=140)
    xs = [float(arm["cost_usd"]) for arm in arms]
    ys = [float(arm["accuracy"]) for arm in arms]
    labels = [display_label(arm["label"]) for arm in arms]
    ax.set_xlabel("Modal dollars for the arm")
    ax.set_ylabel("Accuracy against the full-menu call")
    ax.set_ylim(-0.06, 1.12)
    if xs:
        span = max(xs) - min(xs)
        pad = max(0.02, span * 0.22, max(abs(value) for value in xs) * 0.05)
        ax.set_xlim(min(xs) - pad * 0.55, max(xs) + pad * 2.6)
    ax.set_title(title)
    ax.grid(True, alpha=0.3, zorder=0)
    fig.tight_layout()
    draw_labeled_scatter(ax, xs, ys, labels)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def write_both(arms: list[dict], title: str, repo_path: Path, media_path: Path) -> None:
    write_cost_accuracy_plot(arms, repo_path, title)
    write_cost_accuracy_plot(arms, media_path, title)
