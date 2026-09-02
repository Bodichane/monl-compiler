"""Écrire le contrat et le brief, et les sceller."""

import hashlib
import json
import os

from ..artifacts import (
    chemin_pret,
    copy_preserved_files,
    publish_files,
    staging_directory,
)
from ..ir import CompilationIR
from . import assemblage, brief, fondations, projet


def generate_frontend_contract(normalized_ast: CompilationIR, plans_or_generator,
                               output_dir, spec_name="spec.ml"):
    """Écrit le contrat depuis l'IR et les plans partagés, transactionnellement."""
    contract = assemblage.build_contract(normalized_ast, plans_or_generator)

    target_dir = os.path.abspath(output_dir)
    with staging_directory(target_dir) as temporary:
        copy_preserved_files(
            target_dir, temporary,
            (fondations.AGENTS_FILENAME, fondations.README_FILENAME))
        contract_path = os.path.join(temporary, fondations.CONTRACT_FILENAME)
        with open(contract_path, "w", encoding="utf-8") as fh:
            json.dump(contract, fh, ensure_ascii=False, indent=2, sort_keys=True)
        with open(chemin_pret(temporary, fondations.PROMPT_FILENAME),
                  "w", encoding="utf-8") as fh:
            fh.write(brief._render_prompt(contract))
        projet.write_project_claude_md(contract["app"], temporary, spec_name)
        publish_files(temporary, target_dir, fondations.FRONTEND_ARTIFACTS)
    return contract

def contract_sha256(output_dir):
    path = os.path.join(output_dir, fondations.CONTRACT_FILENAME)
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()
