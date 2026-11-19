"""Write the contract and the brief, and seal them."""

import hashlib
import json
import os

from ..artifacts import (
    copy_preserved_files,
    path_pret,
    publish_files,
    staging_directory,
)
from ..ir import CompilationIR
from . import assembly, brief, foundations, project


def generate_frontend_contract(normalized_ast: CompilationIR, plans_or_generator,
                               output_dir, spec_name="spec.ml"):
    """Writes the contract from the IR and the shared plans, transactionally."""
    contract = assembly.build_contract(normalized_ast, plans_or_generator)

    target_dir = os.path.abspath(output_dir)
    with staging_directory(target_dir) as temporary:
        copy_preserved_files(
            target_dir, temporary,
            (foundations.AGENTS_FILENAME, foundations.README_FILENAME))
        contract_path = os.path.join(temporary, foundations.CONTRACT_FILENAME)
        with open(contract_path, "w", encoding="utf-8") as fh:
            json.dump(contract, fh, ensure_ascii=False, indent=2, sort_keys=True)
        with open(path_pret(temporary, foundations.PROMPT_FILENAME),
                  "w", encoding="utf-8") as fh:
            fh.write(brief._render_prompt(contract))
        project.write_project_claude_md(
            contract["app"], temporary, spec_name,
            contract.get("api", {}).get("auth", {}).get("features"))
        publish_files(temporary, target_dir, foundations.FRONTEND_ARTIFACTS)
    return contract

def contract_sha256(output_dir):
    path = os.path.join(output_dir, foundations.CONTRACT_FILENAME)
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()
