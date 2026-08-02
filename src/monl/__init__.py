"""monl — compilateur d'intention logicielle et orchestrateur frontend.

Le paquet expose la chaîne complète : parseur (grammaire Lark), validateur
et audit de sécurité, générateur de backend, contrat frontend, dialogue
guidé et interface en ligne de commande.

POINT 65 : jusqu'à la bêta 3, ces modules vivaient à plat dans src/ et
n'étaient importables qu'en manipulant sys.path — dans le shim d'entrée
comme en tête de chaque fichier de tests. C'est désormais un vrai paquet :
`from monl.parser import parse_monl_string` fonctionne partout où monl est
installé, sans préparatif.
"""

# POINT 85 : ce numéro n'avait pas bougé des points 74 à 85 — cinq briques, un
# outil, un correctif de sécurité. Il ne disait donc rien, et le point 81 a dû
# construire sa détection d'artefacts périmés sur une RÉGÉNÉRATION plutôt que
# sur lui. Il reste secondaire par construction : la version n'est pas une
# preuve, la recompilation en est une. Mais un numéro faux est pire qu'un
# numéro secondaire — il est désormais enregistré dans monl.json, pour que
# l'avertissement du point 81 puisse dire AVEC QUOI le projet a été construit.
__version__ = "0.9.0-beta.6"
