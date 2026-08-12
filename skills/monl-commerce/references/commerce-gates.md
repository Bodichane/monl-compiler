# Commerce acceptance criteria

- Product/listing cards expose title, media when available, price, and stock or availability.
- Zero stock cannot be purchased.
- Cart quantity changes preserve stock limits and recalculate the visible estimate.
- Checkout identifies the delivery/customer record required by the contract.
- Order confirmation displays the server reference and server total when returned.
- Payment calls send no amount when the contract marks it server-derived.
- Paid state is read from persisted server state, never inferred from browser return alone.
- Seller/admin fulfillment is distinct from buyer order history.
- Conflict, partial completion, and unavailable payment service receive specific recovery copy.
