import unittest

from context_auditor.domain.enums import PrivacyMode
from context_auditor.domain.text import (
    hash_text,
    normalize_text,
    normalized_hash,
    redact_text,
    store_text,
)


class TextPolicyTests(unittest.TestCase):
    def test_normalizes_case_and_space(self):
        self.assertEqual(normalize_text("  Hello \n WORLD  "), "hello world")

    def test_normalization_is_unicode_aware(self):
        self.assertEqual(normalize_text("硕士  论文"), "硕士 论文")

    def test_hash_is_stable_sha256(self):
        self.assertEqual(len(hash_text("context")), 64)
        self.assertEqual(hash_text("context"), hash_text("context"))

    def test_normalized_hash_collapses_formatting(self):
        self.assertEqual(normalized_hash("A  B"), normalized_hash(" a b "))

    def test_redacts_email(self):
        self.assertNotIn("user@example.com", redact_text("email user@example.com"))

    def test_redacts_phone(self):
        self.assertNotIn("+1 202-555-0199", redact_text("call +1 202-555-0199"))

    def test_redacts_bearer_token(self):
        self.assertEqual(redact_text("Bearer abc.def"), "Bearer [REDACTED]")

    def test_redacts_api_key_assignment(self):
        self.assertIn("[REDACTED]", redact_text("api_key=secret-value"))

    def test_redacts_long_hex_secret(self):
        self.assertEqual(
            redact_text("token " + ("a" * 40)),
            "token [REDACTED_SECRET]",
        )

    def test_full_mode_preserves_text(self):
        self.assertEqual(store_text("raw text", PrivacyMode.FULL), "raw text")

    def test_hash_only_mode_removes_text(self):
        stored = store_text("raw text", PrivacyMode.HASH_ONLY)
        self.assertTrue(stored.startswith("[HASH:"))
        self.assertNotIn("raw text", stored)


if __name__ == "__main__":
    unittest.main()
