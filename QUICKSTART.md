# QuickStart — monl

Allow about 5–10 minutes for your first backend, plus time for an optional
interface. Follow the five steps below to generate a backend, optionally add
an interface and accounts, then launch it. Backend generation is deterministic
and offline; installation downloads the package, and optional AI interface
generation may use the network.

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
the build metadata (`monl.json`) and frontend contract (`frontend_contract.json`,
a description of API routes, fields and permissions for the interface), and the
`docs/FRONTEND_PROMPT.md` brief (content and interface instructions).

## 3. Add the optional frontend to `<App>/frontend/`

Choose one method, or skip this step to explore the API first. The brief
`<App>/docs/FRONTEND_PROMPT.md` supplies the instructions for AI methods.

- **Manually**: place the files directly in `<App>/frontend/`.
- **Without any API key** — paste the contents of `docs/FRONTEND_PROMPT.md` into
  any browser-accessible assistant, retrieve the result, then:
  ```bash
  monl import <file-or-zip> <App>
  ```
  The result passes exactly the same safeguards as an API response
  (allowed file types, rejection of external hosted dependencies, consistency,
  and a smoke test: a quick automatic test that starts the app and calls its routes).
- **With a command-line agent** (subscription authentication):
  ```bash
  monl frontend <App> --provider claude-code
  ```
- **With an Anthropic API key**:
  ```bash
  export ANTHROPIC_API_KEY="sk-…"
  monl frontend <App> --provider claude
  ```

Installation may download dependencies; project generation never accesses the
network. Only optional interface generation uses AI, with a no-key route available.

## 4. Privileged accounts (if needed)

`POST /register` accepts only roles marked `selfRegister` in the spec.
Create the others on the machine hosting the database, in the project folder:

```bash
python3 manage.py adduser owner Admin     # prompts for a password
python3 manage.py users                   # list accounts
```

## 5. Verification and launch

```bash
monl run <App>
```

`monl run` checks consistency between the backend, contract, and frontend
(including a smoke test: a quick automatic test that starts the app and calls its routes), then starts the server at
http://127.0.0.1:8000 — interface at `/site`, API documentation at `/docs`.

Open http://127.0.0.1:8000/docs: you see interactive API documentation and can
try the routes against your database. With a frontend installed, open
http://127.0.0.1:8000/site to see the website. Without one, `/docs` is your starting point.

### Optional provider settings

**With another OpenAI-dialect API** (`groq`, `openai`, `mistral`,
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


---

**Evolving the specification.** After changing the spec, `monl update
<App>` resynchronizes the backend and contract and regenerates the update brief (instructions for adapting the interface).
Keep changes in the spec; never edit generated backend code.
Deployment and security model: `docs/SECURITE.md`. Full guide: `README.md`.
