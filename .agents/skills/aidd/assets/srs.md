# Software requirements specification: {{title}}

Generated on {{today}} at {{head}} by `aidd new srs {{target}}`. Never edit it: change a Spec, then generate it again.

<!-- The outline follows ISO/IEC/IEEE 29148:2018, clause 9.6. aidd fills each section from the work items and git,
     and says "none recorded" where they hold nothing, so an empty section is a finding. A requirement is one
     Acceptance item of a Spec at or past Spec approval. It links the test command that covers it (`covers` in the
     Spec's `tests.commands`) and the newest commit that names its Spec. The file lives in `.aidd/views/`, which git
     ignores: the tech writer exports it at handover, and the compliance analyst under the audited profile. -->

## 1. Introduction

### 1.1 Purpose

{{purpose}}

### 1.2 Scope

{{scope}}

### 1.3 Product perspective and functions

{{perspective}}

### 1.4 Users and stakeholders

{{stakeholders}}

### 1.5 Constraints, assumptions, and dependencies

{{constraints}}

## 2. References

{{references}}

## 3. Specific requirements

### 3.1 External interfaces

{{interfaces}}

### 3.2 Functional requirements

{{requirements}}

### 3.3 Other requirements

Each group is a risk dimension that a Spec names (`risk.dimensions`), with the requirements of those Specs. They also appear in 3.2. aidd does not guess a kind from the words of a requirement.

{{other}}

## 4. Verification

{{verification}}

## Appendix A. Work not in this document

{{excluded}}
