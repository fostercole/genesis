"""Cost-versus-accuracy scatter. Local only; the Modal image does not import this."""

from __future__ import annotations

from pathlib import Path


def write_cost_accuracy_plot(arms: list[dict], path: Path, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    xs = [float(arm["cost_usd"]) for arm in arms]
    ys = [float(arm["accuracy"]) for arm in arms]
    ax.scatter(xs, ys, s=90, zorder=3)
    for arm, x, y in zip(arms, xs, ys):
        ax.annotate(arm["label"], (x, y), textcoords="offset points", xytext=(7, 6))
    ax.set_xlabel("Modal dollars for the arm")
    ax.set_ylabel("Accuracy against the full-menu call")
    ax.set_ylim(-0.05, 1.05)
    ax.set_title(title)
    ax.grid(True, alpha=0.3, zorder=0)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def write_both(arms: list[dict], title: str, repo_path: Path, media_path: Path) -> None:
    write_cost_accuracy_plot(arms, repo_path, title)
    write_cost_accuracy_plot(arms, media_path, title)
