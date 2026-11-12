#!/usr/bin/env bash
set -euo pipefail
# A small enrolment record in Ruby, in a repository that uses aidd: its dates end in `_on`, its instant in `_at`, and its statuses
# are bare words. The prompt proposes three names, and two of them borrow another kind's form. The files are ours and are written
# only inside the case's workspace.
mkdir -p .aidd lib
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@org/leads"]
YAML
cat > lib/enrolment.rb <<'RUBY'
# One student's place on one course.
Enrolment = Struct.new(
  :student_id,   # the student
  :course_id,    # the course
  :status,       # one of STATUSES
  :enrolled_at,  # when the student enrolled
  :starts_on,    # the day the course starts
  :ends_on,      # the day the course ends
  :withdrawn_on, # the day the student withdrew, or nil
  keyword_init: true
)

STATUSES = %w[active withdrawn].freeze
RUBY
