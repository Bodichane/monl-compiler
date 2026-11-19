"""Load the spec, and have the compiler PROVE the result.

Revalidation runs WITHOUT `base_dir`: the existence of what the tool
writes is checked separately. A guarantee that is too broad is not safer,
it is wrong elsewhere (point 84)."""

import contextlib
import io

from ..ast_validator import MonlAST
from ..parser import parse_monl_string
from .foundations import AssetsToolError


# -------------------------------------------------- reading the spec --
def _validate(text, spec_path):
    """The real parser and the real validator, WITHOUT base_dir. On purpose.

    It is the exact scope the tool needs, and it comes from layer 1's
    form/existence split: the form checks are pure, so they apply; the
    EXISTENCE check does not — and that is what is needed.

    Two reasons, both discovered by exercising the tool, not by rereading it.
    `monl assets list` could not report a missing asset: loading the spec
    with base_dir failed on that very missing asset, so the report refused to
    run in the only case where it was useful. And `add` was unusable on a
    spec declaring two missing photos — impossible to place one, since the
    other made revalidation fail.

    The existence of what the tool WRITES is checked separately, with the
    same resolver as the compiler (`resoudre_asset`): the guarantee remains,
    it is simply stated correctly. The validator prints its security audit —
    already seen at compile time: it is muted."""
    with contextlib.redirect_stdout(io.StringIO()):
        raw = parse_monl_string(text, file_path=spec_path)
        return MonlAST(raw).validate_and_audit()

def _charger(spec_path):
    """Starting state. Refusing early on an already broken spec is not
    excessive zeal: without this check, the failure of the post-edit
    revalidation would blame the tool for a defect that existed before it."""
    with open(spec_path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        return _validate(text, spec_path)
    except Exception as err:
        raise AssetsToolError(
            f"The spec does not compile as it stands: {err}\n"
            f"   The tool will not write to it while it is broken — otherwise "
            f"the next failure could appear to come from the tool.") from None

def _revalidate(text, spec_path):
    """THE check that makes this tool safe: is the resulting spec valid?

    Reparsed by the real parser, revalidated by the real validator — all of
    the compiler's refusals therefore apply to what the tool has just written.
    That is what ensures layer 2 cannot produce what layer 1 refuses."""
    try:
        return _validate(text, spec_path)
    except Exception as err:
        raise AssetsToolError(
            f"Write CANCELLED — the resulting spec would not compile: {err}\n"
            f"   Neither the spec nor the assets directory was modified.") from None
