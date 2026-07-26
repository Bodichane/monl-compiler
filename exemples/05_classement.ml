app TopVote

# ─────────────────────────────────────────────────────────────────────
# CLASSEMENT COMMUNAUTAIRE COMPLET — archétype "liste classée".
# 'Entry' est en lecture publique et porte un compteur 'score' que les votes
# font monter : la landing en dérive un classement trié (podium pour le top
# 3). Les entrées de démonstration remplissent le classement dès l'ouverture.
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

# Entrées de démonstration avec scores variés (le tri les classera).
seed Entry
    name: "Projet Solaris", score: 128, tagline: "Panneaux solaires imprimés en 3D."
    name: "Application Trille", score: 87, tagline: "Apprentissage musical par le jeu."
    name: "Réseau Maillage", score: 203, tagline: "Internet communautaire hors réseau."
    name: "Atelier Récup", score: 45, tagline: "Réparation d'objets entre voisins."
    name: "Jardin Vertical", score: 66, tagline: "Potagers d'intérieur autonomes."
    name: "Carte Sonore", score: 12, tagline: "Cartographie des paysages sonores urbains."

landing
    brief: "TopVote met en avant les projets communautaires les plus soutenus. Votez pour faire monter vos favoris."
