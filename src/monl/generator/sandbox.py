"""Empty shells of the 'custom' blocks (sandbox_ai.py)."""

from string import Template

_CUSTOM_FUNCTION = Template('''def ${name}(context: dict) -> dict:
    """
    Purpose: ${description}
    """
    # TODO:
    return {'message': 'Deterministic empty shell for ${name}'}
''')


def _docstring_literal(text):
    """A backslash in the spec stays a backslash in the emitted docstring."""
    return text.replace("\\", "\\\\")


class SandboxMixin:
    def _generate_ai_sandbox(self):
        """Generates the shells to complete by hand, without normalizing the bytes.

        substitute does not reinterpret dollars/braces in the values; the
        description is inserted into a NON-raw docstring, so its backslashes are
        doubled: otherwise `\\N` or `\\x` make sandbox_ai.py invalid.
        SQL stays exclusively behind the generator/sql.py boundary."""
        sb_lines = ["# 'custom' BLOCKS — business logic to complete by hand (deterministic)\n"]
        for func in self.custom_functions:
            sb_lines.append(_CUSTOM_FUNCTION.substitute(
                name=func["name"],
                description=_docstring_literal(
                    func.get("description", "Custom business logic.").strip()),
            ))
        return "\n".join(sb_lines)
