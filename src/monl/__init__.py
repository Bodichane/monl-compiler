"""monl — software intent compiler and frontend orchestrator.

The package exposes the complete chain: parser (Lark grammar), validator
and security audit, backend generator, frontend contract, guided dialogue
and command line interface.

POINT 65: until beta 3, these modules lived flat in src/ and could only be
imported by manipulating sys.path — in the entry shim as at the top of
each test file. It is now a real package: `from monl.parser import
parse_monl_string` works wherever monl is installed, with no preparation."""

# POINT 85: this number had not moved from points 74 to 85 — five bricks, one
# tool, one security fix. It therefore said nothing, and point 81 had to build
# its stale-artifact detection on a REGENERATION rather than on it. It stays
# secondary by construction: the version is not a proof, the recompilation is.
# But a wrong number is worse than a secondary one — it is now recorded in
# monl.json, so that the point 81 warning can say WHAT the project was built
# with.
__version__ = "1.0.1"
