app StudioNova

# Spécification générée par le dialogue guidé monl (déterministe, sans IA).
# Brief du projet : portoflio pour photographe

entity Project
    title: String
    description: Text
    imageUrl: String
    category: String

entity Message
    author: String
    email: Email
    content: Text

actor Admin selfRegister

rule Project.title required
rule Message.author required
rule Project.Read public
rule Message.Create public

workflow ManageProject for Admin
    Create Project
    Read Project
    Update Project
    Delete Project

workflow ManageMessage for Admin
    Create Message
    Read Message
    Update Message
    Delete Message

seed Project
    title: "Refonte Aurora", description: "Identité complète pour une marque de cosmétiques.", imageUrl: "https://loremflickr.com/1600/900/art?lock=1", category: "Identité"
    title: "App Meridian", description: "Application mobile de suivi d'habitudes.", imageUrl: "https://loremflickr.com/1600/900/art?lock=2", category: "Produit"
    title: "Site Horizon", description: "Site éditorial pour un festival de musique.", imageUrl: "https://loremflickr.com/1600/900/art?lock=3", category: "Web"

landing
    brief: "portoflio pour photographe — le visiteur doit pouvoir parcourir le site et conctacter l'admin du site ; registre affirmé et graphique : grandes échelles typographiques, contrastes marqués, parti pris visuel assumé ; les images portent le site (photo, œuvre, produit) : elles occupent de grandes surfaces et commandent la mise en page"
    section "À propos": "Je m’appelle Alexandre Moreau et je suis photographe professionnel basé à Paris. Animé par la création visuelle et la quête de précision, je mets mon expertise au service de vos projets depuis maintenant plus de 8 ans. ¶ Mon travail se situe à l'intersection de la rigueur technique et de la créativité graphique. Spécialisé dans la photographie de mode, d'architecture et le corporate, je me distingue par un sens aigu de la composition, des lignes épurées et une gestion méticuleuse des contrastes. ¶ Ce qui caractérise mon approche, c’est ma capacité à transformer une idée, un visage ou un espace en une image forte. Je ne me contente pas de documenter : je structure le cadre, je sculpte la lumière et j'élimine le superflu pour ne garder que l'essentiel. Chaque projet est une opportunité de traduire un concept en une esthétique visuelle percutante, moderne et mémorable, pensée pour valoriser votre identité, vos designs ou l'image de votre marque."
    section "Services": "J'accompagne les marques, les agences, les architectes et les professionnels dans la création d'un patrimoine visuel fort. Mon objectif est de traduire votre identité et vos réalisations à travers des images percutantes, épurées et haut de gamme. ¶ Voici mes trois domaines d'intervention :1. Photographie d'Architecture & Design d'IntérieurPour qui : Architectes, designers d'intérieur, promoteurs immobiliers, hôtels et espaces de coworking. ¶ Ce que je propose : Un travail méticuleux sur les lignes, les perspectives et la lumière naturelle pour valoriser la structure et l'atmosphère de vos espaces. Idéal pour vos books de réalisations, vos publications éditoriales ou votre communication digitale. ¶ 2. Mode, Éditorial & LookbooksPour qui : Marques de prêt-à-porter, créateurs d'accessoires, agences de mannequins et magazines. ¶ Ce que je propose : Des séances photo en studio ou en extérieur (lifestyle urbain) pour donner vie à vos collections. Je gère la direction artistique visuelle pour créer des lookbooks et des campagnes qui capturent l'ADN de votre marque et marquent les esprits. ¶ 3. Corporate & Portrait BusinessPour qui : Entreprises, dirigeants, indépendants et équipes créatives. ¶ Ce que je propose : Des portraits professionnels modernes et valorisants (loin des clichés figés du corporate classique) ainsi que des reportages en immersion dans vos locaux. Idéal pour humaniser votre site web, alimenter vos réseaux professionnels (LinkedIn) et illustrer vos rapports annuels."
