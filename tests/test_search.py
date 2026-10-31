"""Offline tests for the external-search adapter contract."""

import json
import unittest

from shared.search import MockSearchProvider, search_products


class SearchTests(unittest.TestCase):
    def test_search_normalizes_and_bounds_results(self) -> None:
        provider = MockSearchProvider(
            [
                {
                    "title": "Comfortable pearl wedding flats",
                    "url": "https://example.invalid/flats",
                    "price": 89,
                    "currency": "USD",
                    "seller": "Example Shop",
                    "checked_at": "2026-10-31T12:00:00Z",
                    "excerpt": "Soft ivory flats with pearl detail.",
                    "extra_unneeded_field": "discard me",
                }
            ]
        )
        result = search_products(provider, "pearl wedding flats", limit=1)
        self.assertEqual(result["status"], "ok")
        product = result["results"][0]
        self.assertEqual(product["source"], "external_unverified")
        self.assertNotIn("extra_unneeded_field", product)
        self.assertLessEqual(len(json.dumps(result)), 1200)

    def test_provider_errors_are_compact(self) -> None:
        result = search_products(MockSearchProvider([], error="offline"), "wedding flats")
        self.assertEqual(result, {"status": "error", "error": "RuntimeError", "results": []})

    def test_invalid_queries_and_limits_are_rejected(self) -> None:
        provider = MockSearchProvider([])
        with self.assertRaises(ValueError):
            search_products(provider, " ")
        with self.assertRaises(ValueError):
            search_products(provider, "shoes", limit=11)


if __name__ == "__main__":
    unittest.main()
