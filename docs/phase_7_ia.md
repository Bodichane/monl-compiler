# 🟢 Phase 7 — Translation by Local Artificial Intelligence

> **Historical document — feature removed in 0.9.0-beta.2.** Natural-language
> to DSL translation (`--prompt`) and interpretation of free-form answers
> (`--nl`), both based on a local model (Ollama), have been removed: the
> compiler is now fully deterministic. This page remains as a design record. See `CHANGELOG.md`.

## Goal
The goal of this final phase is to complete the compiler by placing an Artificial Intelligence layer before the pipeline. The user expresses a functional need in natural language (French), and AI automatically generates a valid monl specification file, removing the need to write syntax by hand.

## Technical Choices & Low-RAM Optimizations
To ensure full network independence and smooth execution on consumer hardware (8 GB RAM), these choices were made:
- **Inference engine**: `llama-cpp-python` running precompiled GGUF models.
- **Model**: `Qwen2.5-Coder-3B-Instruct` quantized to 4-bit (`Q4_K_M`), limiting memory usage to 2.2 GB RAM.

## Operation and Prompts
The `src/ai_translator.py` script wraps a strict *System Prompt* that acts as a grammar rule dictionary. AI extracts concepts from the user's request (Entities, Attributes, Relations, Actors, Workflows) and returns raw monl code, ready for the Parser (Phase 3).
