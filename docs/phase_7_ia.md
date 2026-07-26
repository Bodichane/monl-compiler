# 🟢 Phase 7 — Traduction par Intelligence Artificielle Locale

> **Document historique — fonctionnalité retirée en 0.9.0-beta.2.** La
> traduction langage naturel → DSL (`--prompt`) et l'interprétation des
> réponses libres (`--nl`), toutes deux fondées sur un modèle local (Ollama),
> ont été supprimées : le compilateur est désormais entièrement déterministe.
> Cette page est conservée comme trace de conception. Voir `CHANGELOG.md`.

## Objectif
L'objectif de cette ultime phase est de couronner le compilateur en plaçant une couche d'Intelligence Artificielle en amont du pipeline. L'utilisateur exprime son besoin fonctionnel en langage naturel (français), et l'IA génère automatiquement le fichier de spécification monl valide, éliminant tout besoin d'écriture syntaxique manuelle.

## Choix Techniques & Optimisations Low-RAM
Pour garantir une indépendance réseau absolue et une exécution fluide sur une configuration matérielle grand public (8 Go de RAM), les choix suivants ont été opérés :
- **Moteur d'inférence** : `llama-cpp-python` exécutant des modèles au format GGUF pré-compilés.
- **Modèle** : `Qwen2.5-Coder-3B-Instruct` quantifié en 4-bits (`Q4_K_M`), limitant l'empreinte mémoire à 2,2 Go de RAM.

## Fonctionnement et Prompts
Le script `src/ai_translator.py` encapsule un *System Prompt* strict agissant comme un dictionnaire de règles de grammaire. L'IA extrait les concepts de la demande de l'utilisateur (Entités, Attributs, Relations, Acteurs, Workflows) et restitue un code monl brut, immédiatement consommable par le Parser (Phase 3).
