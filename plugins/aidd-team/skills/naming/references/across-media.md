# One concept across media, and code identifiers

Load this when you name a field, type, function, column, component, token, screen, or label, or carry a concept from one medium to another.

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
