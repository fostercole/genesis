"""Point names on the cost-versus-accuracy graph stay readable."""

import unittest

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from frontier_plot import display_label, draw_labeled_scatter, write_cost_accuracy_plot


def _name_artists(ax):
    artists = [text for text in ax.texts if text.get_text().strip()]
    legend = ax.get_legend()
    if legend is not None:
        artists.extend(text for text in legend.get_texts() if text.get_text().strip())
    return artists


def _separated(fig, ax) -> None:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    boxes = []
    for artist in _name_artists(ax):
        box = artist.get_window_extent(renderer)
        boxes.append(box.expanded(1.02, 1.08))
    for index, box in enumerate(boxes):
        for other in boxes[index + 1 :]:
            if box.overlaps(other):
                raise AssertionError("label boxes overlap")
        frame = fig.bbox
        if box.x0 < -1 or box.y0 < -1 or box.x1 > frame.x1 + 1 or box.y1 > frame.y1 + 1:
            raise AssertionError("label sits outside the figure")


class CostAccuracyLabelTests(unittest.TestCase):
    def test_keyword_arm_is_never_titled_bm25(self):
        self.assertEqual(display_label("BM25"), "keyword search")
        self.assertEqual(display_label("bm25"), "keyword search")
        self.assertEqual(display_label("keyword search"), "keyword search")

    def test_close_points_keep_separated_names(self):
        fig, ax = plt.subplots(figsize=(8.2, 5.1), dpi=140)
        xs = [0.07339497784990964, 0.0759840279712171, 0.07426843177145247, 0.09292051572396602, 0.0]
        ys = [0.75, 0.75, 0.625, 1.0, 0.75]
        labels = ["tuned 2B top 10", "BM25", "original Open-Jev-2B top 10", "full menu", "hosted Jev top 10"]
        ax.set_xlim(-0.02, 0.16)
        ax.set_ylim(-0.06, 1.12)
        ax.set_title("probe")
        fig.tight_layout()
        draw_labeled_scatter(ax, xs, ys, labels)
        names = [artist.get_text() for artist in _name_artists(ax)]
        self.assertIn("keyword search", names)
        self.assertTrue(all("bm25" not in name.lower() for name in names))
        _separated(fig, ax)
        plt.close(fig)

    def test_identical_points_still_identify_every_arm(self):
        fig, ax = plt.subplots(figsize=(8.2, 5.1), dpi=140)
        xs = [0.2, 0.2, 0.2]
        ys = [0.5, 0.5, 0.5]
        labels = ["full menu", "BM25", "tuned 2B top 10"]
        ax.set_xlim(0.0, 0.4)
        ax.set_ylim(0.0, 1.0)
        fig.tight_layout()
        draw_labeled_scatter(ax, xs, ys, labels)
        names = [artist.get_text() for artist in _name_artists(ax)]
        self.assertEqual(names.count("keyword search"), 1)
        self.assertIn("full menu", names)
        self.assertIn("tuned 2B top 10", names)
        self.assertTrue(all("bm25" not in name.lower() for name in names))
        _separated(fig, ax)
        plt.close(fig)

    def test_plot_writes_a_non_empty_png(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pi-cost-accuracy.png"
            write_cost_accuracy_plot(
                [
                    {"label": "full menu", "cost_usd": 0.4, "accuracy": 1},
                    {"label": "BM25", "cost_usd": 0.2, "accuracy": 0.5},
                ],
                path,
                "probe",
            )
            data = path.read_bytes()
            self.assertTrue(data.startswith(b"\x89PNG"))
            self.assertGreater(len(data), 0)


if __name__ == "__main__":
    unittest.main()
