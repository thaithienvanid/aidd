#!/usr/bin/env bash
set -euo pipefail
# A small premium calculator in Java, in a repository that uses aidd under the solo profile. It prices a policy from a base
# amount and a risk factor, and its one test passes. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd src/main/java/quote src/test/java/quote
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: solo
YAML
cat > src/main/java/quote/Premium.java <<'JAVA'
package quote;

public final class Premium {
    private Premium() {}

    /** The yearly premium in cents: the base amount times the risk factor, rounded to the cent. */
    public static long yearlyCents(long baseCents, double riskFactor) {
        return Math.round(baseCents * riskFactor);
    }
}
JAVA
cat > src/test/java/quote/PremiumTest.java <<'JAVA'
package quote;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class PremiumTest {
    @Test
    void aRiskFactorOfOneKeepsTheBase() {
        assertEquals(12_000L, Premium.yearlyCents(12_000L, 1.0));
    }
}
JAVA
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A && git commit -q -m "feat: yearly premium"
