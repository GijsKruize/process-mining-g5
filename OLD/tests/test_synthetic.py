"""Unit tests for the synthetic logs and the top-k role grouping.

Run from the project root:  python -m unittest discover tests -v
"""
import unittest

import pandas as pd

from OLD.orgmining.roles import OTHER_ROLE, ResourceRoleGrouper
from OLD.orgmining.synthetic import (ACTIVITY_DEPARTMENT, SyntheticLogGenerator, employees,
                                     gold_standard_table, match_roles_to_departments,
                                     translate_gold)


class GeneratorTest(unittest.TestCase):
    def test_same_seed_same_log(self):
        first, _ = SyntheticLogGenerator(50, noise=0.2, seed=7).generate()
        second, _ = SyntheticLogGenerator(50, noise=0.2, seed=7).generate()
        pd.testing.assert_frame_equal(first, second)

    def test_without_noise_every_event_is_done_by_its_department(self):
        log, cases = SyntheticLogGenerator(100, noise=0.0).generate()
        truth = employees()
        departments = log["org:resource"].map(truth)
        self.assertTrue((departments == log["concept:name"].map(ACTIVITY_DEPARTMENT)).all())
        self.assertTrue((cases["noise"] == "").all())
        self.assertEqual(log["case:concept:name"].nunique(), 100)

    def test_noise_level_is_respected(self):
        _, cases = SyntheticLogGenerator(1000, noise=0.3, seed=1).generate()
        self.assertAlmostEqual((cases["noise"] != "").mean(), 0.3, delta=0.05)

    def test_parallel_activities_occur_in_both_orders(self):
        log, _ = SyntheticLogGenerator(200, noise=0.0).generate()
        orders = set()
        for _, events in log.groupby("case:concept:name"):
            activities = list(events["concept:name"])
            if "Check-fraud" in activities:
                orders.add(activities.index("Check-fraud") < activities.index("Validate-documents"))
        self.assertEqual(orders, {True, False})


class GoldTranslationTest(unittest.TestCase):
    def test_departments_are_mapped_to_discovered_roles(self):
        resource_roles = pd.DataFrame({
            "resource": ["Intake_1", "Intake_2", "Offer_1", "Offer_2"],
            "role": ["Role_2", "Role_2", "Role_1", "Role_2"]})
        mapping, purity = match_roles_to_departments(resource_roles)
        self.assertEqual(mapping, {"Intake": "Role_2", "Offer": "Role_1"})
        self.assertEqual(purity, 0.75)
        gold = translate_gold(gold_standard_table(), mapping)
        self.assertEqual(gold.loc[0, "edges"], "Register_Role_2 -> Check-completeness_Role_2")


class TopKRolesTest(unittest.TestCase):
    def test_small_roles_become_other(self):
        log, _ = SyntheticLogGenerator(200, noise=0.0).generate()
        all_roles = ResourceRoleGrouper().fit(log, "org:resource")
        top2 = ResourceRoleGrouper(top_k=2).fit(log, "org:resource")
        self.assertEqual(all_roles.n_roles, 4)               # the four departments
        self.assertEqual(top2.n_roles, 3)                    # Role_1, Role_2 and Other
        self.assertIn(OTHER_ROLE, set(top2.mapping.values()))
        with self.assertRaises(ValueError):
            ResourceRoleGrouper(top_k=0)


if __name__ == "__main__":
    unittest.main()
