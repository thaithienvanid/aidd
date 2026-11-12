"""The headroom line: after a change, text that is always loaded sits at or under
budgets.LINE of its cap, so the next honest edit has room and nobody trims a rule to fit. A file above the line today is in
budgets.ABOVE_THE_LINE with the real limit it is near, and that list only shrinks: a listed file that came under the line must
leave it.

Every cap states the cost it tracks (budgets.CAPS): the test holds the stated tokens and share to the cap's number, so a number
raised without its cost fails, and a cap left as a snapshot of a file's size is not a cost.
"""

import unittest

import budget_shares
import budgets


def rows() -> dict[str, budget_shares.Share]:
    return {r.key: r for r in budget_shares.shares()}


class HeadroomLineTests(unittest.TestCase):
    def test_a_budgeted_file_above_the_line_is_listed_with_a_reason(self):
        found = [r for r in rows().values() if r.group not in budget_shares.CLASS_GROUPS and r.share > budgets.LINE and r.key not in budgets.ABOVE_THE_LINE]
        self.assertEqual(
            [],
            [budgets.make_room(r.key, r.size, r.cap, r.unit) for r in found],
            "A file may not sit above the line after a change. Do not add it to ABOVE_THE_LINE to pass: make room.",
        )

    def test_the_list_only_shrinks(self):
        by_key = rows()
        gone = sorted(set(budgets.ABOVE_THE_LINE) - set(by_key))
        self.assertEqual(gone, [], "a listed budget no longer exists: remove it from ABOVE_THE_LINE")
        under = sorted(k for k in budgets.ABOVE_THE_LINE if by_key[k].share <= budgets.LINE)
        classes = sorted(k for k in budgets.ABOVE_THE_LINE if by_key[k].group in budget_shares.CLASS_GROUPS)
        self.assertEqual(classes, [], "a file that loads on a signal has a class limit and no headroom line: it is never listed here")
        self.assertEqual(under, [], "these files came under the line: remove each from ABOVE_THE_LINE, so the list only shrinks")

    def test_every_listed_file_says_which_real_limit_it_is_near_and_what_would_relieve_it(self):
        for key, near in budgets.ABOVE_THE_LINE.items():
            with self.subTest(key):
                for part in (near.limit, near.relief):
                    self.assertGreater(len(part.split()), 5, "name the limit the file is near, and what would relieve it")
                    self.assertNotIn("{", part, "a reason template was left unfilled")
                self.assertNotIn("its cap was set", near.limit, "a snapshot of a file's size is not a limit")

    def test_the_list_holds_only_what_is_near_a_real_limit(self):
        # With caps that track a cost, the text that is always loaded is under the line, and a class of file that loads on a signal
        # has no line: what is left is code and the two instruction texts and one description.
        groups = {k.split(":")[0] for k in budgets.ABOVE_THE_LINE}
        self.assertLessEqual(groups, {"module", "instructions", "description"})
        self.assertLessEqual(len(budgets.ABOVE_THE_LINE), 13)

    def test_the_failure_message_names_the_file_the_distance_the_cost_and_the_ways_to_make_room(self):
        over = budgets.make_room("config.md", 13177, 12800, cost="it costs 3,200 tokens")
        self.assertIn("config.md is 13,177 bytes, 377 bytes past its cap of 12,800 (102.9%)", over)
        self.assertIn("it costs 3,200 tokens", over)
        above = budgets.make_room("risk.md", 8000, 8704)
        self.assertIn("within its cap of 8,704 bytes but above the 90% line", above)
        for message in (over, above):
            for way in (
                "Restructure by topic",
                "raise the limit, with the cost it tracks written beside it",
                "Never reword, shorten, merge, or drop a rule, a stop, a case, or a fact to fit a number",
                "only where the same reader always loads the other text",
            ):
                self.assertIn(way, message)

    def test_a_file_keeps_to_its_cap_with_the_headroom_and_no_more(self):
        self.assertTrue(budgets.within(12800 * budgets.HEADROOM, 12800))
        self.assertFalse(budgets.within(12800 * budgets.HEADROOM + 1, 12800))

    def test_the_test_sees_every_budget_family(self):
        groups = {r.group for r in budget_shares.shares()}
        self.assertEqual(
            groups,
            {
                "skill",
                "reference",
                "template",
                "role file",
                "role start",
                "instructions",
                "pack skill",
                "practice skill",
                "skill reference",
                "description",
                "module",
            },
        )


class EveryCapStatesItsCostTests(unittest.TestCase):
    def test_a_cap_says_what_it_bounds_who_loads_it_and_what_it_costs(self):
        for name, cap in budgets.CAPS.items():
            with self.subTest(cap=name):
                self.assertTrue(cap.bounds.strip())
                for part in (cap.loaded, cap.cost):
                    self.assertGreater(len(part.split()), 3)
                self.assertNotIn("its size", cap.cost, "a cap is not a file's size on a day")
                self.assertNotIn("{", cap.cost)

    def test_the_stated_bytes_tokens_and_share_are_the_numbers_of_the_cap(self):
        for name, cap in budgets.CAPS.items():
            with self.subTest(cap=name):
                tokens = budgets.tokens(cap.number)
                self.assertIn(f"{cap.number:,} bytes is {tokens:,} estimated tokens", cap.cost)
                self.assertIn(f"{tokens / budgets.WINDOW_TOKENS:.1%} of a 200,000-token window", cap.cost)

    def test_each_cap_named_by_a_constant_is_its_row(self):
        self.assertEqual(
            {k: c.number for k, c in budgets.CAPS.items()},
            {
                "skill": budgets.SKILL_BYTES,
                "graph": budgets.LOOP_BYTES,
                "role file": budgets.ROLE_FILE_BYTES,
                "role start": budgets.ROLE_START_BYTES,
                "reference": budgets.REFERENCE_BYTES,
                "template": budgets.TEMPLATE_BYTES,
            },
        )

    def test_a_size_at_each_cap_with_its_headroom_passes_and_one_byte_past_fails_with_the_cost_and_the_ways_to_make_room(self):
        for name, cap in budgets.CAPS.items():
            with self.subTest(cap=name):
                edge = int(cap.number * budgets.HEADROOM)
                self.assertTrue(budgets.within(edge, cap.number))
                self.assertFalse(budgets.within(edge + 1, cap.number))
                message = budgets.make_room(name, edge + 1, cap.number, cost=budgets.cost_of(name))
                self.assertIn(cap.cost, message)
                self.assertIn("Restructure by topic", message)

    def test_the_pair_a_skill_preloading_role_carries_is_under_60_percent_of_its_start_total(self):
        # The loop's cost line says so: the skill and graph.md leave the rest of the budget to the role file and its other skills.
        self.assertLess(budgets.SKILL_BYTES + budgets.LOOP_BYTES, 0.6 * budgets.ROLE_START_BYTES)
        self.assertIn("under 60% of a role's 14,080-token start total", budgets.CAPS["graph"].cost)
        self.assertEqual(budgets.tokens(budgets.SKILL_BYTES + budgets.LOOP_BYTES), 7680)
        self.assertEqual(budgets.tokens(budgets.ROLE_START_BYTES), 14080)


if __name__ == "__main__":
    unittest.main()
