---
name: monl-commerce
description: Build complete premium commerce and marketplace interfaces for Monl. Use when a contract contains products, listings, prices, stock, carts, orders, purchases, payments, fulfillment, delivery, sellers, or buyers.
---

# Build a Monl commerce experience

Apply `$monl-showcase`, then cover the commercial journey end to end.

## Required journey

1. Present a browsable catalogue with search or useful classification when the fields permit it.
2. Show price and availability next to the purchase decision.
3. Provide a persistent cart or purchase summary with quantity and total feedback.
4. Collect the contract-required customer or delivery profile before ordering.
5. Create the order using only server-authoritative prices and stock.
6. Handle payment redirection, pending state, failure, and unavailable-provider responses honestly.
7. Expose order history and fulfillment controls to the correct roles.

Read [references/commerce-gates.md](references/commerce-gates.md) for acceptance criteria.

Never fabricate payment success, client-side totals as authoritative values, inventory, reviews, delivery promises, or privileged seller controls.
