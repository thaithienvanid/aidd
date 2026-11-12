#!/usr/bin/env bash
set -euo pipefail
# A small grade-book helper in Ruby, in a repository that uses aidd under the solo profile. It averages a student's scores,
# and its one test passes. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd lib test
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: solo
YAML
cat > lib/grades.rb <<'RUBY'
# The mean of a student's scores.
def average(scores)
  scores.sum.to_f / scores.size
end
RUBY
cat > test/test_grades.rb <<'RUBY'
require "minitest/autorun"
require_relative "../lib/grades"

class TestGrades < Minitest::Test
  def test_average_is_the_mean
    assert_in_delta 7.5, average([5, 10])
  end
end
RUBY
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A && git commit -q -m "feat: average"
