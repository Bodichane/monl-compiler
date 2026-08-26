"""Quota de plateforme fondé sur la consommation réelle de monl."""

from dataclasses import dataclass

from monl.usage import UsagePriceError, build_usage_report

from .paths import project_directory


class QuotaError(RuntimeError):
    """Refus de construction lié à la capacité de consommation."""


class QuotaExceededError(QuotaError):
    """Le compte a atteint son quota avant cette construction."""

    def __init__(self, message, *, build_id=None):
        super().__init__(message)
        self.build_id = build_id


class QuotaUnavailableError(QuotaError):
    """La consommation existante est incomplète et ne peut être estimée."""


@dataclass(frozen=True, slots=True)
class QuotaStatus:
    consumed_tokens: int
    limit_tokens: int
    remaining_tokens: int
    project_totals: dict


class TokenQuota:
    """Quota en jetons, volontairement indépendant des prix.

    Le choix des jetons est délibéré : ``monl.usage`` refuse honnêtement de
    calculer un coût si le modèle n'a pas de tarif déclaré. Une plateforme qui
    choisissait l'argent devrait alors refuser ce modèle ou demander un tarif;
    ce socle replie explicitement le contrôle sur les jetons et enregistre
    ``cost = NULL`` au lieu d'inventer un prix.
    """

    def __init__(self, store, workspace_root, max_tokens):
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 0:
            raise ValueError("max_tokens doit être un entier positif ou nul")
        self.store = store
        self.workspace_root = workspace_root
        self.max_tokens = max_tokens

    def inspect(self, account):
        # Le quota reçoit directement l'identifiant texte de l'identité de
        # main ; aucun registre numérique du constructeur ne doit être
        # consulté ici.
        account_id = account
        consumed = 0
        project_totals = {}
        for project in self.store.list_projects(account_id):
            directory = project_directory(
                self.workspace_root, account_id, project["project_id"], create=False
            )
            journal = directory / ".monl_ai_usage.jsonl"
            if not journal.is_file():
                project_totals[project["project_id"]] = 0
                continue
            try:
                report = build_usage_report(str(directory))
            except UsagePriceError:
                # Le quota choisi ne dépend pas du tarif : une table de prix
                # absente ou invalide ne doit pas transformer des jetons connus
                # en un faux zéro. Le rapport sans prix suffit pour les jetons.
                report = build_usage_report(str(directory), prices_path=None)
            total = report["project_total"]["total_tokens"]
            if total is None:
                raise QuotaUnavailableError(
                    f"consommation en jetons indéterminée pour le projet "
                    f"{project['project_id']}")
            project_totals[project["project_id"]] = total
            consumed += total
        return QuotaStatus(
            consumed_tokens=consumed,
            limit_tokens=self.max_tokens,
            remaining_tokens=max(0, self.max_tokens - consumed),
            project_totals=project_totals,
        )

    def ensure_available(self, account):
        status = self.inspect(account)
        if status.consumed_tokens >= status.limit_tokens:
            raise QuotaExceededError(
                f"quota de jetons dépassé : {status.consumed_tokens}/"
                f"{status.limit_tokens} jetons déjà consommés"
            )
        return status
