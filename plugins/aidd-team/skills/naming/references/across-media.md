# One concept across media, and code identifiers

Load this when you name a field, type, function, column, component, token, screen, or label, or carry a concept from one medium to another. Load it too when you name a value, a state, an event, an action, or a derived view in a data model.

**Contents**

<!-- aidd:gen toc -->
- [One concept, every medium](#one-concept-every-medium)
- [Code identifiers](#code-identifiers)
- [Names in a data model](#names-in-a-data-model)
- [Design names](#design-names)
- [Units, money, and time](#units-money-and-time)
- [Prose and tests](#prose-and-tests)
<!-- aidd:end -->

## One concept, every medium

Each medium keeps its own case style. The words stay the same.

| Medium | Style | A tenant | An order total |
| --- | --- | --- | --- |
| TypeScript, JavaScript fields | camelCase | `tenantId` | `totalMinor`, `currency` |
| Python fields | snake_case | `tenant_id` | `total_minor`, `currency` |
| Go | PascalCase exported, camelCase not, initialisms in capitals | `TenantID`, `tenantID` | `TotalMinor` |
| Types and classes | PascalCase | `TenantId` (Go: `TenantID`) | `Money` |
| Database columns | snake_case | `tenant_id` | `total_minor`, `currency` |
| HTTP JSON fields, query parameters | camelCase | `tenantId` | `?minTotalMinor=` |
| HTTP paths | kebab-case, plural nouns | `/tenants/{tenantId}` | `/orders/{orderId}/line-items` |
| CloudEvents attributes | lowercase letters and digits only; should not exceed 20 characters | `tenantid` | in `data`: `totalMinor` |
| OpenTelemetry attributes | lowercase, dot namespaces, snake_case words | `com.example.tenant.id` | metric `billing.invoice.amount` |
| Environment variables | UPPER_SNAKE, app prefix, then the module | `APP_ORDERS_DEFAULT_TENANT_ID` | — |
| Feature flags | `<module>.<feature>`, kebab-case | `identity.tenant-switcher` | `billing.multi-currency` |

## Code identifiers

| Thing | Pattern | Examples |
| --- | --- | --- |
| Module facade | `<Module>Api` | `OrdersApi` |
| Command, which changes state | verb, noun, `Command` | `PlaceOrderCommand` |
| Query | `get` returns or fails, `find` can return nothing, `list` returns many | `getOrder`, `findUser`, `listOpenInvoices` |
| Result across modules | noun and role | `OrderSummary`, `InvoiceDetails` |
| Port to an outside capability | the role it plays | `PaymentProvider`, `EmailSender` |
| Entity, value object | business noun | `Order`, `Money`, `EmailAddress` |
| Repository | `<Entity>Repository` | `OrderRepository` |
| Factory | `create<Thing>` | `createOrdersApi` |
| Event handler | `on<EventName>` | `onOrderPlaced` |
| Job | verb and object | `expireStaleCarts` |
| Error | `<Problem>Error` | `OrderNotFoundError` |
| Collection | plural noun | `lineItems` |
| Boolean | `is`, `has`, `can`, `should`, said positively | `isPaid`, `canRefund` |
| Conversion | `to`, `from`, `parse`, `format` | `toOrderSummary`, `parseMoney` |
| Constant | what the value means | `DEFAULT_PAGE_SIZE` |
| Limit | `max_` or `min_` first | `MAX_LOGIN_ATTEMPTS`, `min_total_minor` |
| Test data builder | `a<Thing>`, `an<Thing>` | `anOrder().withLines(2).build()` |

### A type field

The field that says which variant a thing is takes one word in the whole codebase. Take the word the language or the platform already uses, and write it in the glossary:

| Where | The word | Why |
| --- | --- | --- |
| Rust | `kind`, as in `ErrorKind` | `type` is a keyword |
| Go | `Kind`, as in `reflect.Kind`, or an exported `Type` field | `type` is a keyword, but `Type` is a legal name |
| Kubernetes manifests | `kind` | the platform sets it |
| JSON:API, CloudEvents, schema.org | `type`, `@type` | the standard sets it |
| GraphQL | `__typename` | the standard sets it |
| Most other code and formats | `type` | the common word |

- Never put `type` and `kind` on one object, unless the platform sets one of them.
- Name a second dimension for what it is, never with the other word. `draft` or `final` is a `status`, `card` or `cash` is a payment `method`, and `full` or `partial` is a refund `scope`.
- Nest a true sub-type under its parent, as `payment.method`, or give it a composite key. Never add a second generic word for it.
- In Python, `type` is a builtin. Name a variable for what it holds, such as `doc_type`, and keep `type` for the field in the data.

## Names in a data model

A model holds several kinds of name, and a reader must tell the kind from the form alone. So each kind has one form, and no form serves two kinds. The forms below are common ones. Where the project has its own, the project's win. A project form that already serves two kinds is a finding to report, never a family for a new name to join.

| Kind | What it names | Form | In a library's loans |
| --- | --- | --- | --- |
| Field | a stored fact about one object | a noun, with its family's suffix | `due_on`, `renewal_count` |
| Value | one of the closed set a field holds | a bare word, in the project's case for codes | `paperback`, `audio` |
| State | the object's place in its life | an adjective or a past participle, bare | `on_loan`, `returned` |
| Event | a fact that happened | the object and a verb in the past tense (systems.md, "Events") | `loan.returned` |
| Action | what a caller asks for | a verb and its object, as a command is named above | `renewLoan`, `loan.renew` |
| Derived view | an answer computed when it is read | the plain word people say, marked as computed where it is defined | overdue |

- **A marker belongs to one kind.** A suffix, a prefix, or a separator that marks one kind never appears on another kind. Where `customer_id` is a reference, a boolean named `valid_id` reads as a reference too. Where instants end in `_at`, nothing but an instant does. Before you add a name, list the names that share its last word, its prefix, or its separator. Each name on that list is the same kind of thing, or the new name changes.
- **A value never looks like a path.** A dotted name reads as a field of an object: `loan.overdue` reads as the `overdue` field of a loan. Keep the dot for an event type or an action, where the last part is a verb. Write a state, a value, and a derived view bare.
- **One set holds one kind.** A list that mixes a state, an action, and a derived view makes its reader learn three kinds under one name. `aidd-team:data-model-design` owns the split.
- **Tense tells an action from an event from a state.** The action is the verb (`renew`), the event is its past (`renewed`), and a resting state is an adjective or a past participle, as AIP-216 names states. [aip-216] An event and the state that follows it may share that participle, because they are read in different places. Where two kinds are shown in one place, a prefix alone never tells them apart.

### What should be, and what happened

A model often holds a goal and its record: what should happen, and what did. Give each its own word.

| What should be | What happened |
| --- | --- |
| `due_on`, `promised_on` | `returned_on`, `delivered_on` |
| a target, a budget, a plan, an estimate | an actual, a spend, a result, a reading |

- A goal word never names a record, and a record word never names a goal. Pair them, so a reader sees both sides: a `target` with its `actual`.
- One kind of thing keeps one word at every scope, as an order's `status` and a shipment's `status` do, and where it sits tells the scope. Read it with its owner: "the order's status". A word that is a goal at one scope and a record at another is two ideas, so it needs two words. systems.md, "One word at several scopes", has the test for each.
- A word keeps the sense it has in everyday use. Most readers take "closed" for finished, so an account that is `closed` because it is blocked reads as settled. Say `blocked`.

### Check a model's names

Walk every name of the model through these checks, with the names of each set and family that it joins, and write down each one that fails:

- Group the names by their last word, and again by a first word that marks a kind, such as `is_` or `max_`, and by their separator. Every group holds one kind of thing. Write the groups down, because a clash shows only when the names sit side by side.
- No state, value, or derived view is written with a dot, and no set holds two kinds.
- No name or value joins two facts. A value that needs an "and", or a second noun with its own verb, is two fields (`aidd-team:data-model-design`).
- No word names a goal in one place and a record in another.
- One kind of thing has one word at every scope of a hierarchy. Walk the scopes side by side, as systems.md says ("One word at several scopes").
- Each word is the one the readers' field uses, in its everyday sense, or the glossary says what that word would be confused with.

## Design names

A design's names reach the code, the tests, and the person on the screen, so each holds from the sketch to the shipped product.

- A component and its variants keep one name from design to code. `data-component="order-card"` with `data-variant="compact"` is the `OrderCard` component, its `compact` variant, and its story.
- Name a token by its role, never its value: `color.text.muted`, not `gray-500`. The role token aliases a base value, as the W3C Design Tokens format's aliases do, so a new palette renames nothing.
- Name a screen and a state by the person's task, in the glossary's words: `checkout` and `payment-declined`, not `screen-4` and `error-2`.
- A test id is kebab-case, names what the control does, and stays the same through a redesign, because the frozen tests select on it: `place-order`, not `blue-button-2`.
- A UI label is the word the person knows, the same on every screen (WCAG 2.2 SC 3.2.4). One thing never gets two labels, such as Cart and Basket, and one label never names two things. A label never reads as another meaning beside its neighbor: "Free" next to a price reads as no charge, so say "Available". A control's accessible name contains its visible label (SC 2.5.3).

## Units, money, and time

- Put the unit last: `timeoutMs`, `sizeBytes`, `ttlSeconds`.
- Money is an integer in minor units with a currency: `amountMinor` and `currency`, an ISO 4217 code such as `"EUR"`. Never a float. Never say "cents": the minor unit differs by currency (JPY has none, KWD has three).
- An instant ends in `At` and is UTC: `placedAt`, `placed_at timestamptz`. A date ends in `On`: `dueOn`, `due_on`.

## Prose and tests

- In prose, name the concept: "OrderPlaced". In code, the constant is `ORDER_PLACED_V1` and its data type `OrderPlacedV1Data`.
- A test name says the behavior from the caller's side: `rejects an order with an unknown SKU`. Group tests by the unit under test: `describe('Order.place')`.
