import unittest

from architekton import classifier
from architekton.config import DEFAULTS


class ScoreTest(unittest.TestCase):
    def test_empty_prompt_is_light(self):
        self.assertLess(classifier.score(""), 0.5)

    def test_medium_neutral_prompt_sits_at_base(self):
        self.assertEqual(classifier.score("x" * 400), 0.5)

    def test_heavy_signals_raise_score(self):
        text = "x" * 400 + " refactor and audit the security layer"
        self.assertGreater(classifier.score(text), 0.8)

    def test_light_signals_lower_score(self):
        self.assertLess(classifier.score("fix the typo, rename it"), 0.3)

    def test_repeated_word_counts_once(self):
        once = classifier.score("x" * 400 + " refactor")
        many = classifier.score("x" * 400 + " refactor refactor refactor")
        self.assertEqual(once, many)

    def test_long_prompt_adds_per_doubling(self):
        base = classifier.score("x" * 1700)  # ~425 tokens
        doubled = classifier.score("x" * 3400)  # ~850 tokens
        self.assertGreater(doubled, base)

    def test_length_bonus_is_capped(self):
        self.assertEqual(classifier.score("x" * 400_000), 0.8)

    def test_signals_past_scan_window_are_ignored(self):
        text = "x" * 900 + " refactor"
        self.assertEqual(classifier.score(text), classifier.score("x" * 900 + " nothing"))

    def test_score_is_clamped(self):
        text = " ".join(["refactor architect design review audit debug investigate security exploit"] * 3)
        self.assertLessEqual(classifier.score(text), 1.0)


class ClassifyTest(unittest.TestCase):
    def test_tiers_follow_thresholds(self):
        thresholds = DEFAULTS["thresholds"]
        self.assertEqual(classifier.tier_for_score(0.65, thresholds), "opus")
        self.assertEqual(classifier.tier_for_score(0.30, thresholds), "haiku")
        self.assertEqual(classifier.tier_for_score(0.50, thresholds), "sonnet")

    def test_classify_shape(self):
        result = classifier.classify("what is a typo", DEFAULTS)
        self.assertEqual(set(result), {"score", "tier", "recommended_model"})
        self.assertEqual(result["tier"], "haiku")

    def test_recommended_model_uses_configured_alias(self):
        config = {**DEFAULTS, "models": {**DEFAULTS["models"], "opus": "claude-opus-5-5"}}
        text = "x" * 400 + " refactor and audit the security layer"
        self.assertEqual(classifier.classify(text, config)["recommended_model"], "claude-opus-5-5")


class TierOfModelTest(unittest.TestCase):
    def test_aliases_and_full_ids(self):
        self.assertEqual(classifier.get_tier_of_model("opus"), "opus")
        self.assertEqual(classifier.get_tier_of_model("claude-sonnet-5-5"), "sonnet")
        self.assertEqual(classifier.get_tier_of_model("Haiku"), "haiku")

    def test_unknown_or_missing_is_none(self):
        self.assertIsNone(classifier.get_tier_of_model("gpt-9"))
        self.assertIsNone(classifier.get_tier_of_model(None))


if __name__ == "__main__":
    unittest.main()
