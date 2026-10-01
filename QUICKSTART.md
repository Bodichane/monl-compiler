# QuickStart — monl

Three steps: the guided dialogue generates the backend, the frontend is added to
the target folder, then the application is launched. Operation is deterministic
and offline by default.

## 1. Installation

```bash
pip install monl-compiler
```

Installs the dependencies and the `monl` command. From a repository clone,
`pip install -e .` does the same. To use frontend providers through an API,
also install the optional extra: `pip install 'monl-compiler[ai]'`.

## 2. Project generation (guided dialogue)

```bash
monl
```

The guided dialogue asks a series of questions, then creates a folder named
after the application. This folder contains the backend (`app.py`, `schema.sql`),
the architecture and contract (`monl.json`, `frontend_contract.json`), and the
`docs/FRONTEND_PROMPT.md` brief intended for the interface.

## 3. Add the frontend to `<App>/frontend/`

Four methods are available. The brief `<App>/docs/FRONTEND_PROMPT.md` serves as
the AI instruction in the last three.

- **Manually**: place the files directly in `<App>/frontend/`.
- **Without any API key** — paste the contents of `docs/FRONTEND_PROMPT.md` into
  any browser-accessible assistant, retrieve the result, then:
  ```bash
  monl import <fichier-ou-zip> <App>
  ```
  The result passes exactly the same safeguards as an API response
  (allowlist, CDN rejection, consistency, smoke test).
- **With a command-line agent** (subscription authentication), in the target
  folder:
  ```bash
  monl frontend <App> --provider claude-code
  ```
- **With an Anthropic API key**:
  ```bash
  export ANTHROPIC_API_KEY="sk-…"
  monl frontend <App> --provider claude
  ```
- **With another OpenAI-dialect API** (`groq`, `openai`, `mistral`,
  `ollama`…), specifying the model. Yandex Cloud AI Studio uses the same
  route; the key and folder remain in the environment, and the model ID is the
  one shown by AI Studio:
  ```bash
  export YANDEX_API_KEY='…'
  export YANDEX_FOLDER_ID='…'
  monl frontend <App> --provider yandex \
    --model "gpt://$YANDEX_FOLDER_ID/yandexgpt/latest"
  ```
  If a slow model exceeds the HTTP timeout, lower the response limit for that
  call: `MONL_AI_MAX_TOKENS=8000 monl frontend …`.

Reminder: steps 1 and 2 above never access the network. Only this step uses AI,
and it has a no-key route.

## 3 bis. Privileged accounts

`POST /register` accepts only roles marked `selfRegister` in the spec.
Create the others on the machine hosting the database, in the project folder:

```bash
python3 manage.py adduser patron Admin     # prompts for a password
python3 manage.py users                    # inventaire des comptes
```

## 4. Verification and launch

```bash
monl run <App>
```

`monl run` checks consistency between the backend, contract, and frontend
(including a behavioral smoke test), then starts the server at
http://127.0.0.1:8000 — interface at `/site`, API documentation at `/docs`.

---

**Evolving the specification.** After changing the spec, `monl update
<App>` resynchronizes the backend and contract and regenerates the update brief.
Deployment and security model: `docs/SECURITE.md`. Full guide: `README.md`.
