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
    status: String
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
# L'ordre COMPTE : la relation vers l'acteur d'abord, sinon la colonne
# 'post_id' — visée par 'increments' — sortirait de l'INSERT et
# 'oncePer' porterait sur une colonne toujours NULL (refus à la
# compilation depuis le point 116).
relation Member hasMany Like
relation Post hasMany Like
relation Post hasMany Dislike
relation Post hasMany Repost
relation Post hasMany Comment
relation Member hasMany Comment
relation Member hasMany Report
relation Member hasMany PrivateMessage

actor Member selfRegister

# Modérateur : provisionné hors ligne (manage.py), il LIT et SUPPRIME tous les
# messages privés — le rôle superviseur au-dessus d'accessibleBy (brique 23).
actor Moderator

capability auth

# Posts publics SOUS CONDITION (brique 27) : un post masqué par la modération
# cesse d'être lisible, y compris par son URL directe. Le modérateur, lui,
# continue de le voir — sans quoi masquer voudrait dire perdre — et l'auteur
# retrouve les siens.
rule Post.status oneOf "published", "hidden"
rule Post.Read publicWhen status "published"
rule Post.Read sharedBy Moderator
rule Post.author generated

# Les likes s'affichent en catégories (brique 5).
rule Post.likes categorized: "confidentiel" below 10, "populaire" below 100, "viral" otherwise

# Réactions Twitter-like : like, dislike, repost font monter les compteurs ;
# un signalement baisse la réputation du membre visé.
# Brique 28 : un compte ne like qu'UNE fois chaque post — l'unicité tient à un
# index composite (compte + post), pas à une empreinte fournie par le client.
rule Like.Create oncePer Member, Post
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
# Le modérateur supervise les deux : il voit et supprime tous les messages.
rule PrivateMessage.Read sharedBy Moderator
rule PrivateMessage.Delete sharedBy Moderator

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

workflow Moderate for Moderator
    Read PrivateMessage
    Delete PrivateMessage
    Read Post
    Update Post

# Fil de démonstration : posts publics déjà likés (catégories variées).
# L'auteur affiché sera le pseudonyme anonyme généré, pas ces valeurs — le
# champ 'author' est 'generated', donc le seed ne le renseigne pas.
seed Post
    content: "Premier jour sur RezoAnon. L'anonymat change vraiment la façon de s'exprimer.", status: "published", likes: 4
    content: "Astuce : les likes ne montrent qu'une catégorie, pas un score exact. Moins de course aux chiffres.", status: "published", likes: 42
    content: "Ce post part pour devenir viral, on dirait. Merci à tous !", status: "published", likes: 230
    content: "Question ouverte : préférez-vous l'anonymat total ou un pseudonyme stable ?", status: "published", likes: 17
    content: "La réputation baisse quand on est signalé — ça calme les trolls.", status: "published", likes: 8

landing
    brief: "RezoAnon est un réseau social où les posts sont publics mais les auteurs restent anonymes, les likes s'affichent en catégories, et la réputation protège la communauté."
