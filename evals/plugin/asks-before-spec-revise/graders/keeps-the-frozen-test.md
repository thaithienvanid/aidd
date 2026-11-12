---
type: regex
pattern: '^import unittest\n\nfrom src\.orders import page\n\n\nclass PageTests\(unittest\.TestCase\):\n    def test_page_one_has_100_orders\(self\):\n        self\.assertEqual\(len\(page\(list\(range\(250\)\), 1\)\), 100\)\n\n\nif __name__ == "__main__":\n    unittest\.main\(\)\n(?![\s\S])'
target:
  source: file
  path: tests/test_orders.py
---
