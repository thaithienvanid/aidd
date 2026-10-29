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
| Environment variables | SCREAMING_SNAKE_CASE, app prefix | `APP_DEFAULT_TENANT_ID` | — |
| Feature flags | `<module>.<feature>`, kebab-case | `identity.tenant-switcher` | `billing.multi-currency` |

## Code identifiers

| Thing | Pattern | Examples |
| --- | --- | --- |
| Module facade | `<Module>Api` | `OrdersApi` |
| Factory | `create<Thing>` | `createOrdersApi` |
| Command, which changes state | verb, noun, `Command` | `PlaceOrderCommand` |
| Query | `get` returns or fails, `find` can return nothing, `list` returns many | `getOrder`, `findUser`, `listOpenInvoices` |
| Result across modules | noun and role | `OrderSummary`, `InvoiceDetails` |
| Entity, value object | business noun | `Order`, `Money`, `EmailAddress` |
| Repository | `<Entity>Repository` | `OrderRepository` |
| Error | `<Problem>Error` | `OrderNotFoundError` |
| Event handler | `on<EventName>` | `onOrderPlaced` |
| Job | verb and object | `expireStaleCarts` |
| Boolean | `is`, `has`, `can`, `should`, said positively | `isPaid`, `canRefund` |
| Conversion | `to`, `from`, `parse`, `format` | `toOrderSummary`, `parseMoney` |
| Constant | what the value means | `DEFAULT_PAGE_SIZE` |
| Limit | `max_` or `min_` first | `MAX_LOGIN_ATTEMPTS`, `min_total_minor` |
| Port to an outside capability | the role it plays | `PaymentProvider`, `EmailSender` |
| Collection | plural noun | `lineItems` |
| Test data builder | `a<Thing>`, `an<Thing>` | `anOrder().withLines(2).build()` |

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
