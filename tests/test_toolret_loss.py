import math
import unittest

from toolret_smoke.loss import toolret_nll


class LossTests(unittest.TestCase):
    def test_other_targets_do_not_compete(self):
        # Two targets and one negative. Each softmax is target vs the negative only.
        scores = [2.0, 0.0, -1.0]
        first = toolret_nll([2.0, -1.0], 1)
        second = toolret_nll([0.0, -1.0], 1)
        self.assertAlmostEqual(toolret_nll(scores, 2), (first + second) / 2)

    def test_higher_target_score_lowers_loss(self):
        worse = toolret_nll([0.0, 1.0, 1.0], 1)
        better = toolret_nll([3.0, 1.0, 1.0], 1)
        self.assertLess(better, worse)

    def test_no_negatives_is_zero(self):
        self.assertEqual(toolret_nll([1.5, 0.2], 2), 0.0)

    def test_uniform_is_log_classes(self):
        self.assertAlmostEqual(toolret_nll([0.0, 0.0, 0.0], 1), math.log(3))


if __name__ == "__main__":
    unittest.main()
