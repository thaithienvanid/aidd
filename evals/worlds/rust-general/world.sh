#!/usr/bin/env bash
set -euo pipefail
# A small unit-conversion library in Rust, in a repository that uses aidd under the solo profile. It converts kilometres to
# miles, and its one test passes. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd src
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: solo
YAML
cat > Cargo.toml <<'TOML'
[package]
name = "units"
version = "0.1.0"
edition = "2021"
TOML
cat > src/lib.rs <<'RS'
/// Miles in a number of kilometres.
pub fn km_to_miles(km: f64) -> f64 {
    km * 0.621_371
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ten_km_is_about_six_miles() {
        assert!((km_to_miles(10.0) - 6.21371).abs() < 1e-6);
    }
}
RS
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A && git commit -q -m "feat: km to miles"
