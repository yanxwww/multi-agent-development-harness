import unittest

from src.backend import dogfood_status


class DogfoodStatusTests(unittest.TestCase):
    def test_returns_expected_message(self):
        self.assertEqual(
            dogfood_status(),
            "multi-agent-development-harness dogfood ok",
        )
