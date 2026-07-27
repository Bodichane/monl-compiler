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

__version__ = "0.9.0-beta.3"
