---
description: A request to bump every dependency to latest in one change, majors included, is split into one package or coherent group per change, with majors on their own and the changelog, advisories, and rollback addressed.
plugins:
  - "../.."
  - "../../../.."
max_turns: 25
timeout_seconds: 900
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
tags:
  - practice
---

Our dependencies are ancient. Please update everything in this package.json to the latest version in one pull request so we get it over with.

```json
{
  "dependencies": {
    "express": "4.18.2",
    "react": "18.2.0",
    "react-dom": "18.2.0",
    "left-pad": "1.3.0",
    "lodash": "4.17.20"
  },
  "devDependencies": {
    "eslint": "8.57.0",
    "jest": "29.7.0"
  }
}
```
