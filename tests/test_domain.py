"""Offline tests for shared bridal-shopping records and tools."""

import json
import unittest

from shared.domain import BridalProfile, ProductCandidate, ShoppingDecision
from shared.tools import build_shopping_plan, compare_products, save_decision


class DomainTests(unittest.TestCase):
    def test_profile_rejects_invalid_wedding_date_and_budget(self) -> None:
        with self.assertRaises(ValueError):
            BridalProfile(wedding_date="not-a-date", budget=1000)
        with self.assertRaises(ValueError):
            BridalProfile(wedding_date="2027-06-01", budget=-1)

    def test_plan_is_prioritized_and_omits_purchased_categories(self) -> None:
        profile = BridalProfile(
            wedding_date="2027-06-01",
            budget=3000,
            categories=("dress", "shoes", "accessories"),
            purchased_categories=("dress",),
        )
        plan = build_shopping_plan(profile, as_of="2027-01-01")
        categories = [item["category"] for item in plan["items"]]
        self.assertNotIn("dress", categories)
        self.assertEqual(set(categories), {"shoes", "accessories"})
        self.assertEqual(plan["budget"]["amount"], 3000)
        self.assertEqual(sorted(plan["items"], key=lambda item: item["priority"]), plan["items"])
        json.dumps(plan)

    def test_product_comparison_exposes_budget_and_avoid_violations(self) -> None:
        products = [
            ProductCandidate("a", "Ivory satin heel", 150, tags=("ivory", "heel")),
            ProductCandidate("b", "Pearl ivory flat", 80, tags=("ivory", "flat")),
        ]
        result = compare_products(
            products,
            max_price=100,
            preferred_tags=("flat",),
            avoid_terms=("satin",),
        )
        ranked = result["results"]
        self.assertEqual(ranked[0]["product_id"], "b")
        self.assertIn("over_budget", ranked[1]["violations"])
        self.assertTrue(any(value.startswith("avoid_terms:") for value in ranked[1]["violations"]))

    def test_save_decision_requires_explicit_conflict_confirmation(self) -> None:
        decisions: dict[str, ShoppingDecision] = {}
        original = ShoppingDecision("budget", 1500, "2026-10-31T12:00:00Z", "scenario:1")
        revised = ShoppingDecision("budget", 2000, "2026-10-31T12:05:00Z", "scenario:2")
        self.assertEqual(save_decision(decisions, original)["status"], "saved")
        conflict = save_decision(decisions, revised)
        self.assertEqual(conflict["status"], "conflict")
        self.assertEqual(decisions["budget"].value, 1500)
        self.assertEqual(save_decision(decisions, revised, confirm_revision=True)["status"], "revised")
        self.assertEqual(decisions["budget"].value, 2000)


if __name__ == "__main__":
    unittest.main()
