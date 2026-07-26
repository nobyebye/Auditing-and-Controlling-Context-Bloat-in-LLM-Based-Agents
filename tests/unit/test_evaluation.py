import unittest

from context_auditor.application.evaluation import (
    bootstrap_mean_interval,
    mcnemar_exact_p_value,
)


class EvaluationTests(unittest.TestCase):
    def test_bootstrap_interval_is_deterministic(self):
        first = bootstrap_mean_interval([0.0, 0.5, 1.0], samples=500, seed=7)
        second = bootstrap_mean_interval([0.0, 0.5, 1.0], samples=500, seed=7)

        self.assertEqual(first, second)
        self.assertLess(first[0], 0.5)
        self.assertGreater(first[1], 0.5)

    def test_constant_bootstrap_interval_collapses_to_point(self):
        self.assertEqual(bootstrap_mean_interval([1.0, 1.0]), [1.0, 1.0])

    def test_mcnemar_exact_p_value_is_two_sided(self):
        self.assertAlmostEqual(mcnemar_exact_p_value(0, 5), 0.0625)
        self.assertIsNone(mcnemar_exact_p_value(0, 0))


if __name__ == "__main__":
    unittest.main()
