app FluxBoard

# ─────────────────────────────────────────────────────────────────────
# COMPLETE KANBAN BOARD — team task tracking.
# Public column view (kanban archetype: one column per status, discovered
# at
# runtime) + manager administration. The demo tasks fill the columns from
# the
# first opening.
# ─────────────────────────────────────────────────────────────────────

entity Task
    title: String
    description: Text
    assignee: String
    priority: String
    status: String

actor Manager
actor Contributor selfRegister

rule Task.title required
rule Task.Read public
rule Task.Update sharedBy Manager, Contributor

workflow ManageBoard for Manager
    Create Task
    Update Task
    Delete Task

workflow WorkBoard for Contributor
    Read Task
    Update Task.status

# Demo tasks spread over several statuses (the board's columns are deduced
# from these values) and priorities.
seed Task
    title: "Cadrage du projet", assignee: "Ana", priority: "Haute", status: "À faire", description: "Définir le périmètre et les livrables."
    title: "Recherche utilisateurs", assignee: "Bo", priority: "Moyenne", status: "À faire", description: "5 entretiens à mener cette semaine."
    title: "Maquettes écrans clés", assignee: "Ana", priority: "Haute", status: "En cours", description: "Accueil, détail, tunnel."
    title: "API d'authentification", assignee: "Cy", priority: "Haute", status: "En cours", description: "JWT + révocation."
    title: "Design system", assignee: "Ana", priority: "Basse", status: "En cours", description: "Tokens, composants de base."
    title: "Configuration CI", assignee: "Cy", priority: "Moyenne", status: "Terminé", description: "Tests + build à chaque push."
    title: "Charte graphique", assignee: "Ana", priority: "Moyenne", status: "Terminé", description: "Palette, typographies, logo."

landing
    brief: "FluxBoard est un tableau de suivi de tâches en équipe, organisé par statut, du cadrage à la livraison."
