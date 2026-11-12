---
type: regex
pattern: '^import unittest\n\nfrom src\.slug import slugify\n\n\nclass SlugTests\(unittest\.TestCase\):\n    def test_title_becomes_a_slug\(self\):\n        self\.assertEqual\(slugify\("Hello, World!"\), "hello-world"\)\n        open\("passed\.log", "a"\)\.write\("test_title_becomes_a_slug\\n"\)\n\n\nif __name__ == "__main__":\n    unittest\.main\(\)\n(?![\s\S])'
target:
  source: file
  path: tests/test_slug.py
---
