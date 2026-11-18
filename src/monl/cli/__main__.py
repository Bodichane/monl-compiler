"""`python -m monl.cli`.

Replaces the `if __name__ == "__main__"` the original module carried: a
package cannot run through its `__init__`. The installed entry point stays
`monl = monl.cli:main` (pyproject.toml)."""

from . import main

if __name__ == "__main__":
    raise SystemExit(main())
