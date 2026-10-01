# Reference Application — CodexShop

CodexShop is the stationery shop delivered in `demo/`. It serves as a reference
path for verifying the creation of a shop, an order, and schema evolution while
preserving data. Its specification, interface, and photos are versioned; the
backend and contract are recompiled.

This guide describes the current project. The automated checks below do not
constitute feedback from real users.

## 1. Prepare a working copy

From the repository root, with monl installed in your Python environment
(`pip install -e '.[dev]'` to also get the verification tools):

```bash
projet_demo="$(mktemp -d /tmp/codexshop-XXXXXX)"
cp demo/spec.ml "$projet_demo/"
cp -r demo/frontend demo/assets "$projet_demo/"
monl compile "$projet_demo/spec.ml" --output "$projet_demo"
monl run "$projet_demo" --check
monl run "$projet_demo"
```

Keep this terminal and the value of `projet_demo` for what follows. To keep
the shop permanently, move the temporary directory into your project space
after stopping the server.

Open `http://127.0.0.1:8000/site` for the shop and
`http://127.0.0.1:8000/docs` to explore the generated API.
The copy contains its own `spec.ml`, so an evolution does not modify the
repository example. Compiling `demo/spec.ml` directly to another directory
would retain a reference to the original spec.

## 2. Place an order

In a fresh copy, the catalog contains twelve products. Follow this path in the
interface:

1. Add two **Ivory Linen Notebooks**, at €24 each, to the cart.
2. Create a customer account with an email address as the **identifier**,
   a password of at least eight characters, and a complete delivery record.
   Use fictional data for this local demonstration.
3. Confirm the order and find it in your account.
4. Check the total of **€48**, the `CMD-…` reference, the creation date,
   and the product stock, reduced from **18 to 16**.

The authentication account and delivery record are two distinct objects.
The API refuses to create an order without a record, with status 409.
The interface guides the creation of this record.

The total and subtotals are calculated by the server. To reproduce the calls
from Swagger, use `/register`, then `/login`, and paste the
`access_token` into **Authorize**. After creating the `/customer` record,
create an order with `POST /order`:

```json
{"status": "À confirmer"}
```

Then add its line with `POST /ligneorder`:

```json
{"order_id": 1, "product_id": 1, "quantite": 2}
```

Replace the identifiers with those returned by your API.
Do not send `total`, `sousTotal`, or an order reference.

Without `STRIPE_SECRET_KEY`, the payment request responds **503**, naming the
missing configuration. This is the limit of the local path: no money is
collected. The lines already reserve stock; cancellation restores it.
Payment through the provider and shipment after payment require separate
validation in the provider's test environment.

## 3. Evolve an order without losing it

Stop the server with `Ctrl+C`. In **the copy** `$projet_demo/spec.ml`, add a
line `    note: Text` just after `entity Order`, keeping all existing fields.

```bash
monl run "$projet_demo" --check
monl diff "$projet_demo"
monl update "$projet_demo"
```

The first command must refuse the spec that has not been recompiled. `diff`
lets you read the planned change, then `update` regenerates the backend and
contract and produces `$projet_demo/docs/FRONTEND_UPDATE_PROMPT.md`, which
mentions `Order.note`.
The `app.db` database, accounts, JWT secret, and frontend files are preserved.

To verify the migration on the API side before adapting the interface, start
the backend from the same terminal:

```bash
(cd "$projet_demo" && python -m uvicorn app:app --host 127.0.0.1 --port 8000)
```

Log in to Swagger with the same account. The existing order must keep its
identifier, reference, date, and total; `note` is `null`.
Stock must remain at 16 and the catalog at twelve products: restarting must
neither restore reserved stock nor duplicate the initial data.

With `PUT /order/{id}`, send:

```json
{"status": "À confirmer", "note": "Livrer le matin"}
```

Read the order again to verify the note. Then send twice:

```json
{"status": "Annulée", "note": "Livrer le matin"}
```

Stock returns to 18 and stays there. Stop this server after verification.

This evolution also changes the expected form: `note` must be sent in new
creations and modifications. `update` does not rewrite the interface. Use the
evolution brief to add its input and display to the frontend, then rerun
`monl run "$projet_demo" --check` and the order path. The migration test below
checks the evolved API; it does not claim to adapt or validate this new form.

## 4. Rerun the automated checks

From the repository root:

```bash
python -m pytest tests/test_demo.py tests/test_demo_cycle.py -q
```

These tests require the ability to open local ports. The interface smoke test
uses Node and jsdom; the diagnostics indicate their availability.

| Check | Automated proof |
|---|---|
| Spec, backend, contract, and interface are consistent | `test_demo.py` |
| Standalone interface and API calls at startup | `test_demo.py` |
| Required record, calculated amount, and reduced stock | `test_demo_cycle.py` |
| Order hidden from another customer account | `test_demo_cycle.py` |
| Insufficient stock refused without partial change | `test_demo_cycle.py` |
| Payment explicitly unavailable without a key | `test_demo_cycle.py` |
| Account, token, order, and stock preserved after update | `test_demo_cycle.py` |
| New field usable and cancellation without double restoration | `test_demo_cycle.py` |

The tests work in temporary directories. They do not call any payment provider
and do not modify your working shop.

## 5. Observe a first user

Ask someone unfamiliar with Monl to try the initial copy. Give them a goal
(“order two notebooks, then find the order”) and observe the steps before
offering explanations. For the operator path, have a developer follow the
preparation and evolution sections.

For each session, record:

| Task | Completed without help? | Duration | Observed blockage or message |
|---|---|---|---|
| Launch the shop from the guide | To be filled in | To be measured | To be filled in |
| Create an account and complete delivery details | To be filled in | To be measured | To be filled in |
| Place an order and find its reference and amount | To be filled in | To be measured | To be filled in |
| Understand why local payment is unavailable | To be filled in | To be measured | To be filled in |
| Update the spec and find the order again | To be filled in | To be measured | To be filled in |

Note the Monl version and the exact reproduction steps, without any password
or token. Prioritize fixes for blockages that prevent completing a task or
undermine confidence in the amount, stock, or data preservation. No user
results have yet been recorded in this guide.
