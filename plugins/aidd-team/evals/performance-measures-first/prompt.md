---
description: A request to add caching to a slow page is answered with a budget, a baseline measurement taken before any edit, and the N+1 query the code shows, fixed and guarded by a query-count test, before any cache.
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
  - Bash
  - Write
  - Edit
tags:
  - practice
---

The orders page is slow for our bigger customers, it takes several seconds. Let's just put a Redis cache in front of it. Here is the view, in `orders.py` (`db.py` stands in for the ORM and counts the queries); make the change:

```python
def orders_page(request):
    orders = Order.objects.filter(account=request.account).order_by("-created_at")
    rows = []
    for order in orders:
        rows.append({
            "id": order.id,
            "customer": order.customer.name,
            "items": order.items.count(),
            "total": order.total,
        })
    return render(request, "orders.html", {"rows": rows})
```
