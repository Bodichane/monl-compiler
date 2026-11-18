app TopVote

# ─────────────────────────────────────────────────────────────────────
# COMPLETE COMMUNITY RANKING — "ranked list" archetype.
# 'Entry' is publicly readable and carries a 'score' counter that votes
# raise: the landing derives a sorted ranking from it (podium for the top 3).
# The demo entries fill the ranking from the first opening.
# ─────────────────────────────────────────────────────────────────────

entity Entry
    name: String
    tagline: Text
    score: Integer

entity Vote
    note: String

relation Entry hasMany Vote

actor Participant selfRegister

rule Entry.name required
rule Entry.Read public
rule Vote.Create increments Entry.score by 1

workflow Submit for Participant
    Create Entry
    Read Entry

workflow CastVote for Participant
    Create Vote

# Demo entries with varied scores (sorting will rank them).
seed Entry
    name: "Projet Solaris", score: 128, tagline: "Panneaux solaires imprimés en 3D."
    name: "Application Trille", score: 87, tagline: "Apprentissage musical par le jeu."
    name: "Réseau Maillage", score: 203, tagline: "Internet communautaire hors réseau."
    name: "Atelier Récup", score: 45, tagline: "Réparation d'objets entre voisins."
    name: "Jardin Vertical", score: 66, tagline: "Potagers d'intérieur autonomes."
    name: "Carte Sonore", score: 12, tagline: "Cartographie des paysages sonores urbains."

landing
    brief: "TopVote met en avant les projets communautaires les plus soutenus. Votez pour faire monter vos favoris."
