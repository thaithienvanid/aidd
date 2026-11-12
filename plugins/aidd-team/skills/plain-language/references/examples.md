# Examples: before and after

Load this when a rule in the skill needs a shape to copy. Find the row for the rule. Copy the shape of the After text, never its words. The rows come from unrelated products, so none of their words are yours.

## The reader's task

| Rule | Before | After |
| --- | --- | --- |
| The next action | I refactored three modules, renamed the helpers, updated the docs, and the build now takes 4 minutes. Please review. | Please approve the new retry limit, 3 to 5. The other edits are renames. |
| The answer first | I looked at the logs, then compared both configs, and after some tests I think the cache is the cause. | The cache causes the slow page. The logs show 40 misses a second, and the page is fast with the cache off. |
| A condition before the action | Click Remove. Check that the account has no open orders first. | Check that the account has no open orders. Then click Remove. |
| No label the reader never saw | Option B from this morning fixes the P2 item. | Moving the upload to a background job fixes the timeout on files over 50 MB. |
| The reader's words | The principal's entitlement check failed. | You cannot open this report, because your account has no access to it. |
| What is unknown, said once | The fix should probably work, and it might also help the mobile app, I believe. | The fix works on the web app. It is not tested on the mobile app. |
| A cut the reader would not miss | "Great question! To answer what you asked about the export, it is really very simple. Let me know if you need more." | The export is under Settings, then Data. |

## Sentences

| Rule | Before | After |
| --- | --- | --- |
| One instruction in each sentence | Stop the worker and then, once the queue has drained, restart it and check the log. | 1. Stop the worker. 2. Wait until the queue is empty. 3. Start the worker. 4. Check that the log shows `ready`. |
| Words in an instruction | Before you restart the service, which reads its settings only at start, make sure that every worker has finished the job it is running. | Wait until every worker finishes its job. Then restart the service, because it reads its settings only at start. |
| A paragraph on one topic | The cache keeps pages for an hour. It needs 2 GB. Logs rotate daily. Old logs move to cold storage. Backups run at night. They take an hour. They are encrypted. | Two paragraphs, one for the cache and one for the logs and backups. |
| The active voice, with who acts | The invoice is sent after approval is given. | The system sends the invoice after the manager approves it. |
| The reason with the rule | Do not restart the server during a backup. | Do not restart the server during a backup, because a restart corrupts the archive. |
| Clauses joined by a word | Do not restart during a backup: the archive breaks (a restart corrupts it). | Do not restart during a backup, because a restart corrupts the archive. |
| One term for one thing | Open the workspace. In the project, pick a folder. | Open the workspace. In the workspace, pick a folder. |
| A term spelled out at first use | Restart the SSO proxy. | Restart the single sign-on (SSO) proxy. |
| The specific thing | The page loads slowly. | The page takes 6 seconds to load on a mobile connection. |
| A split that keeps its qualifier | Refund the order. Do this only for items that have not shipped. | Refund the order only if its items have not shipped. |
| An exact error, copied | If the build fails, the message says it cannot find the config file. | If the build fails with `Error: config.yml not found`, add the file. |
| A number with its unit | The timeout is 30. The trial ends on 03/04/2027. | The request stops after 30 seconds. The trial ends on 2027-04-03. |

## Messages

| Rule | Before | After |
| --- | --- | --- |
| An error says what happened and the next step | Error: invalid input. | The file `report.csv` has no header row. Add a first row with the column names, then upload the file again. |
| A warning before an irreversible step, in full sentences | Warning: destructive! | This deletes all 214 orders, and you cannot undo it. Type the shop's name to confirm. |

## Text an agent reads

An agent follows the strongest form it gets.

| Rule | Before | After |
| --- | --- | --- |
| The exact command and the reason | Be careful with migrations and avoid risky changes. | Before a migration, run `make backup`. Stop if it fails, because a failed backup leaves no rollback. |
| Closed values | Set a sensible priority. | Set `priority` to `low`, `normal`, or `high`. |
| A case and its answer | Small changes usually need less review, but bigger ones may need more. | A table with one row for each size of change, and a column for the review that size gets. |

## The form

| Rule | Before | After |
| --- | --- | --- |
| A table when each row answers the same questions | The Small plan has 5 seats and costs 10 EUR a month, Team has 20 seats for 40 EUR, and Business has no seat limit and costs 200 EUR. | A table with one row for each plan, and the columns Seats and Price a month. |
| Prose when the text gives a reason | A table with the columns Rule and Reason, and one word in each cell. | Keep the backup for 30 days, because the audit asks for one month of history. |
| Items with no order, in one stated order | Bullets in the order someone thought of them: Low, Critical, Medium, High. | Bullets from the most severe: Critical, High, Medium, Low. |
| Data a program reads | The result: build passed, 12 tests, no warnings. | `{"build": "passed", "tests": 12, "warnings": 0}` |

## A rewrite that loses nothing

List the facts before you rewrite or cut. Cut only the words that carry no fact. Then check the list again.

| Rule | Before | The facts | After |
| --- | --- | --- | --- |
| A cut keeps every fact | We are pleased to let you know that, in this release, an export feature has been added, which covers the last 90 days of data and can be run by admins only. | The export is new. It holds 90 days. Only an admin runs it. | New in this release, an admin can export the last 90 days of data. |
| A rewrite keeps a commitment | Delivery of the export may be possible in March, subject to the audit being passed. | It is a "may", not a "will". The audit is its condition. | If the audit passes, we may deliver the export in March. |
