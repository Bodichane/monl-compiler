app RezoAnon

# ─────────────────────────────────────────────────────────────────────
# RÉSEAU SOCIAL COMPLET — consolide tous les exemples sociaux :
#   • posts publics avec auteur ANONYME généré par le serveur (jamais
#     fourni par le client) ;
#   • likes affichés en CATÉGORIES (peu / populaire / viral) plutôt qu'en
#     nombre exact ;
#   • RÉPUTATION des membres qui baisse en cas de signalement ;
#   • messages PRIVÉS accessibles au seul expéditeur et destinataire ;
#   • commentaires publics, modifiables par leur seul auteur.
# Le fil s'affiche déjà peuplé grâce aux données de démonstration.
# ─────────────────────────────────────────────────────────────────────

entity Member
    name: String
    reputation: Integer

entity Post
    content: Text
    author: String
    likes: Integer
    dislikes: Integer
    reposts: Integer

entity Comment
    content: Text

entity Like
    note: String

entity Dislike
    note: String

entity Repost
    note: String

entity Report
    reason: String

entity PrivateMessage
    content: Text
    recipient_id: Integer

relation Member hasMany Post
relation Post hasMany Like
relation Post hasMany Dislike
relation Post hasMany Repost
relation Post hasMany Comment
relation Member hasMany Comment
relation Member hasMany Report
relation Member hasMany PrivateMessage

actor Member selfRegister

capability auth

# Posts publics ; l'auteur est un pseudonyme anonyme stable généré serveur.
rule Post.Read public
rule Post.author generated

# Les likes s'affichent en catégories (brique 5).
rule Post.likes categorized: "confidentiel" below 10, "populaire" below 100, "viral" otherwise

# Réactions Twitter-like : like, dislike, repost font monter les compteurs ;
# un signalement baisse la réputation du membre visé.
rule Like.Create increments Post.likes by 1
rule Dislike.Create increments Post.dislikes by 1
rule Repost.Create increments Post.reposts by 1
rule Report.Create decrements Member.reputation by 10

# Commentaires publics en lecture, éditables par leur seul auteur.
rule Comment.Read public
rule Comment.Update ownedBy Member
rule Comment.Delete ownedBy Member

# Messagerie privée : expéditeur (member_id auto) ET destinataire seulement.
rule PrivateMessage.Read accessibleBy member_id, recipient_id
rule PrivateMessage.Delete accessibleBy member_id, recipient_id

workflow Onboard for Member
    Create Member

workflow Publish for Member
    Create Post
    Read Post

workflow Interact for Member
    Create Like
    Create Dislike
    Create Repost
    Create Report

workflow Discuss for Member
    Create Comment
    Read Comment
    Update Comment
    Delete Comment

workflow DirectMessage for Member
    Create PrivateMessage
    Read PrivateMessage
    Delete PrivateMessage

# Fil de démonstration : posts publics déjà likés (catégories variées).
# L'auteur affiché sera le pseudonyme anonyme généré, pas ces valeurs — le
# champ 'author' est 'generated', donc le seed ne le renseigne pas.
seed Post
    content: "Premier jour sur RezoAnon. L'anonymat change vraiment la façon de s'exprimer.", likes: 4
    content: "Astuce : les likes ne montrent qu'une catégorie, pas un score exact. Moins de course aux chiffres.", likes: 42
    content: "Ce post part pour devenir viral, on dirait. Merci à tous !", likes: 230
    content: "Question ouverte : préférez-vous l'anonymat total ou un pseudonyme stable ?", likes: 17
    content: "La réputation baisse quand on est signalé — ça calme les trolls.", likes: 8

landing
    brief: "RezoAnon est un réseau social où les posts sont publics mais les auteurs restent anonymes, les likes s'affichent en catégories, et la réputation protège la communauté."
