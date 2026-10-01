# The monl-compiler license, explained

> This document **explains** the license; it does not modify it or add any
> conditions. In case of conflict, only the text of [LICENSE](LICENSE) governs.

monl-compiler is released under **FSL-1.1-ALv2** — the *Functional Source
License*, with automatic conversion to Apache-2.0. The text is unchanged from
the version published at [fsl.software](https://fsl.software).

## What changed from the old license

The old proprietary license reserved “use of the software, including for
internal or personal purposes.” In other words: the repository was readable,
and nothing more. That is no longer the case.

**You can now**, without asking:

- use monl-compiler, including professionally and commercially;
- install it internally, in your CI, or at your clients' sites;
- modify it, fork it, and derive works from it;
- redistribute it under the same conditions;
- use it for services you charge for.

This last point is explicit in the license (*Permitted Purposes*, point 4): an
agency or independent contractor can use monl-compiler to deliver applications
to clients and charge for that service.

## The only prohibited activity: competing use

The license prohibits a **Competing Use**: making the software available to
third parties in a commercial product or service that substitutes for it or
offers identical or substantially similar functionality.

For monl-compiler, in practical terms:

| You want to… | Permitted? |
|---|---|
| Compile your own applications, for yourself or a client | Yes |
| Sell application development done with monl-compiler | Yes |
| Teach or study monl-compiler outside a commercial setting | Yes |
| Fork it and publish your fixes under the same license | Yes |
| Launch an online service that compiles monl specs for third parties | No |
| Include the compiler in your own commercial low-code product | No |

These last two cases are not permanently closed: they require a commercial
license — open an *issue* at <https://github.com/Bodichane/monl-compiler>.

## You own the applications you produce

The license covers **the compiler and its tooling**, not what they generate.
The `app.py`, `schema.sql`, `manage.py`, and frontends produced from **your**
specifications belong to you: you can host, modify, and maintain them freely,
including after any commercial relationship ends. No monl-compiler component
is bundled into the generated application, and it never calls monl at runtime.

The generated application's **third-party dependencies** (FastAPI, Lark,
PyJWT, uvicorn, psycopg…) remain under their respective licenses.

## Conversion to Apache-2.0

Each published version becomes available under **Apache-2.0 two years after its
release**. The countdown is **per version**, not global:

- `v0.9.0-beta.7`, published on **August 12, 2026**, will be under Apache-2.0
  on **August 12, 2028**;
- a version published in 2027 will convert in 2029.

This conversion is **irrevocable**: it is granted in the license text itself,
at publication. It does not depend on any later decision by the rights holder.

## What is no longer reserved

For transparency, two reservations from the old license have disappeared
because the FSL is reproduced unchanged and does not contain them:

- **training models on this code** is no longer explicitly prohibited;
- integrating it into other software is now permitted, as long as it does not
  constitute a competing use.

This is the accepted cost of a standard license that is recognizable and
readable by compliance tools, instead of custom text that every legal team
would need to analyze.

## Contributions

Outside contributions are not open at this time (see [CONTRIBUTING.md](CONTRIBUTING.md)).
Bug reports and feedback are still welcome in the *issues*.
