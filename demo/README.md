# CodexShop — the versioned demo

An online stationery shop: public catalog, multi-item cart, orders
paid and then shipped. Produced by the complete monl-compiler workflow, from
the guided dialogue through to the interface — the latter written by Codex against the
contract.

**Three inputs, the only ones that are written:**

| File | Written by |
|---|---|
| `spec.ml` | the guided dialogue, based on the author's answers |
| `frontend/` | an interface AI, against the contract produced by monl-compiler |
| `assets/` | the human — product photos and a home page visual (brick 13) |

Everything else — backend, contract, brief, project state — is recalculated from
`spec.ml` in a second, and therefore lives in the compilation directory, not here.
Versioning it has already made it silently go stale once (point 68): the
delivered contract dated from before three compiler improvements.

## Run it again

```bash
projet_demo="$(mktemp -d /tmp/codexshop-XXXXXX)"
cp demo/spec.ml "$projet_demo/"
cp -r demo/frontend demo/assets "$projet_demo/"
monl compile "$projet_demo/spec.ml" --output "$projet_demo"
```

```bash
monl run "$projet_demo" --check
```

```bash
monl run "$projet_demo"
```

The copy has its own specification: you can evolve it without
modifying the repository's. The [reference workflow](../docs/DEMO.md) details
a command, the schema update, and the observations to record during a
first user trial. The temporary directory must be moved to your project
space if you want to keep it long term.

The photos are served because `serve.py` mounts `assets/` at
`/site/assets` as soon as the directory exists — the frontend references them by a RELATIVE path
(`assets/carnet-lin.webp`), never by an absolute URL.

## What the test suite does with it

`tests/test_demo.py` recompiles this spec, places this frontend and these assets in it,
then requires the whole thing to pass the consistency check **and** the behavioral smoke
test — the interface is actually run in jsdom against an ephemeral
server, and the test refuses a frontend that has not called any
route. The demo therefore cannot silently rot.

A second test checks that the frontend remains AUTONOMOUS: extensions on the
allowlist (`.html`, `.css`, `.js`, `.svg`, `.json`), no remote scripts,
no CDN. The photos are exempt from this list because they live outside
`frontend/` — that is the whole point of brick 13.

`tests/test_demo_cycle.py` also exercises the real spec over HTTP: account, record,
order at €48, stock, separation of customers, then `monl update` with a note added. It checks
that the data, token, and frontend are preserved,
as well as the single restoration of stock on cancellation. External payment
and adapting the form after adding the note remain outside this test.

## What it shows about the language

This is the complete commerce chain, the one that cost the most points in the
design journal:

- `derivedFrom` then `sumOf`: the line subtotal and order total are CALCULATED
  by the server, never written by the client
  (points 77 to 82);
- `payable` on that total, meaning an amount no one can set
themselves, and the lock that freezes the order once paid (point 91);
- `decrements … by champ`: stock decreases by what was ordered, and
  increases again if the line disappears (points 86 and 92);
- `oneOf` and `writableAfterPayment`: the shipping status advances after
  payment, but only by the administrator and through a dedicated route
  (points 96 and 113);
- `numbered`: the order reference that you give over the phone, assigned
  by the server (point 102);
- `requiresOwn`: no order without a customer record, to avoid a parcel that
  no one can ship (point 90);
- `releases`: cancelling an order returns the stock it held, only once,
  and the cancelled state is terminal (point 98);
- `timestamp`: the order date is written by the server at creation and
  never afterward — a date you assign yourself proves nothing
  (point 89).
