app EtudeIsolation

entity Note
    titre: String

actor Auteur selfRegister

relation Auteur hasMany Note

rule Note.Read ownedBy Auteur

custom Publier
    description: "Etude isolation"
    input: titre: String
    output: resultat: String

workflow Ecrire for Auteur
    Create Note
    Read Note
    Execute Publier
