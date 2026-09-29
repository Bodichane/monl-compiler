# Publish monl-compiler with Trusted Publishing

This procedure publishes `monl-compiler` without a long-lived secret. A `v*`
tag triggers `.github/workflows/publication.yml`, which tests and lints the
commit tagged, builds the distributions once, sends them first to TestPyPI,
then waits for approval from the protected `pypi` environment before sending
them to PyPI.

The workflow has no stored username, password, or token. The PyPA action asks
GitHub for a short-lived OIDC identity; PyPI verifies it and then issues a
temporary upload authorization. Local tests do not upload anything.

## Platform image

The tag also triggers `.github/workflows/platform-image.yml`. This workflow
rebuilds `Dockerfile.platform`, checks the installed modules, `/ready`, the
Docker healthcheck, and the non-root user, then publishes the validated image
as `ghcr.io/bodichane/monl-platform:<tag>`. It also publishes `latest` for a
tag and `edge` when triggered manually.

To use the image on a server, make the GHCR package accessible to that server
and set `MONL_PLATFORM_IMAGE` to a specific tag in `.env`. The image is never
pushed with a repository secret: the workflow uses the ephemeral
`GITHUB_TOKEN` and the `packages: write` permission.

## Account prerequisites

PyPI no longer accepts passwords for uploads. To publish, the maintainer must
use Trusted Publishing or, only as a fallback, an API token.

2FA is required on the account that administers or publishes on PyPI. It must
be enabled before configuring the trusted publisher.

TestPyPI is a separate instance from PyPI:

- a separate account and registration at `test.pypi.org`;
- a separate verification email address, or at minimum separate verification
  of the address on that instance;
- a separate project, trusted publisher, and environment;
- 2FA must also be active on the TestPyPI account used to configure it.

So a registration or verified address on PyPI grants no access to TestPyPI,
and vice versa.

## Configure the trusted publisher on PyPI

The maintainer performs this configuration in their browser, with 2FA
enabled. They do not create, copy, or enter a token.

For an existing project, open **Your projects → Manage → Publishing** on the
relevant instance. For `monl-compiler` before its first upload, open
**Account → Publishing**, choose a pending publisher, and also fill in the
name of the project to create. A pending publisher allows the project to be
created on the first successful upload, without any token; it does not reserve
the name in the meantime.

On PyPI, add a **GitHub Actions** publisher with these fields:

| PyPI field | Value to enter |
| --- | --- |
| Project | `monl-compiler` |
| Repository owner | `Bodichane` |
| Repository | `monl-compiler` |
| Workflow | `publication.yml` |
| Environment | `pypi` |

The Workflow field is the filename under `.github/workflows`, not the
readable name `Publication` displayed by GitHub Actions. The maintainer
repeats the same process on `test.pypi.org` (a separate TestPyPI account),
with exactly these values:

| TestPyPI field | Value to enter |
| --- | --- |
| Project | `monl-compiler` |
| Repository owner | `Bodichane` |
| Repository | `monl-compiler` |
| Workflow | `publication.yml` |
| Environment | `testpypi` |

The values `pypi` and `testpypi` are the names declared in the workflow. A
typo in the owner, repository, file, or environment results in an
`invalid-publisher` refusal that the action cannot fix.

Finally, in **GitHub → Settings → Environments**, create or check the `pypi`
environment and add the maintainer as a **required reviewer**. The `testpypi`
environment can have its own rules, but mandatory manual approval is the gate
that protects the final upload to PyPI.

## Before building

The distribution name remains `monl-compiler`. Checking it requires no
authentication:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' \
  https://pypi.org/pypi/monl-compiler/json
```

`404` means the API does not yet return a project for this name; `200` means
it is already taken. In the latter case, stop and choose another name:
`twine` does not create a second project.

## What the workflow checks

The workflow is deliberately triggered by `push.tags: ["v*"]`, never by a
branch push: merging into `main` does not publish. The verification job
compares the tag with the `pyproject.toml` version using
`packaging.version.Version`. Thus `0.9.0-beta.8` and `0.9.0b8` are recognized
as the same Python version; string equality would incorrectly refuse this
valid publication. A mismatch names both values and stops the pipeline before
building.

Tests and `ruff check src tests` run in this workflow on the commit designated
by the tag, before the build job. The CI for `main` is not sufficient proof: it
may have tested a different commit.

The `build` job runs `rm -rf dist/` in that order, then builds exactly once
with `python -m build`. It validates the wheel and source archive, then passes
the same files through `upload-artifact`. The publishing jobs use
`download-artifact`.

Do not rebuild between the two uploads, to TestPyPI and PyPI. An uploaded
version is final and cannot be reused, even after deletion; a stale artifact
in `dist/` could therefore publish the wrong version.

## Manual fallback path only

This path is documented for the exceptional case where Trusted Publishing is
unavailable. It is not part of the normal workflow. A password is not
suitable for a PyPI upload: an API token is required, with the literal
username `__token__` and a token value beginning with `pypi-`. The token stays
only in the maintainer's keychain or personal `~/.pypirc`, never in this
repository, a ticket, a log, or a copied command. This guide uses no secret
value, and the OIDC path uses neither `TWINE_PASSWORD` nor the `--password`
option.

If this fallback path is actually chosen, `~/.pypirc` can contain the public
addresses of both indexes, with no secret in this excerpt:

```ini
[distutils]
index-servers =
    testpypi
    pypi

[testpypi]
repository = https://test.pypi.org/legacy/

[pypi]
repository = https://upload.pypi.org/legacy/
```

From the repository root, first check the name and version. Cleanup must
precede building: `dist/` is ignored by git but persists from one build to the
next on a publishing machine.

```bash
rm -rf dist/
python -m build
python -m twine check dist/*
unzip -l dist/*.whl
```

**`rm -rf dist/` is not a style precaution; this is measured.** `dist/` is
ignored by git, so it does not exist in a freshly cloned repository—but it
persists on a machine that has already built, which is precisely the machine
that publishes. Observed on the maintainer's machine when writing this:
`dist/` contained `monl_compiler-0.9.0b7` while the version to publish was
`0.9.0b8`, and `dist/anciens/` still contained artifacts named
`monl-0.9.0b5`, that is, the OLD distribution name. Building without cleanup
leaves both side by side, and `dist/*` then expands to all four files:
**`twine upload` would publish a version we did not intend to send, and that
cannot be removed from an index**—PyPI does not allow republishing a version
number, even after deletion. The `monl-0.9.0b5` artifacts would also create a
SECOND project on the index. `twine check` and `unzip -l dist/*.whl` also
become ambiguous, so their checks no longer show what they applied to.

In the workflow, `dist/` does not exist at the start—each run starts on a
fresh machine. The `rm -rf dist/` is retained there anyway: when someone adds
a cache between two steps, the guarantee must already be in place.

The first build command must produce a source archive (`.tar.gz`) and a wheel
(`.whl`). `twine check` must validate both, and the wheel must in particular
contain `monl_platform/static/`, the modules, grammar, templates, application
models, and `*.dist-info/licenses/LICENSE`.

Do not use `dist/anciens/`: this directory may contain artifacts with the old
distribution name `monl-0.9.0b5`. Uploading them would create a second
project on the index.

The same files in `dist/` are then used for both indexes. Do not rebuild
between the two uploads:

```bash
python -m twine upload --repository testpypi dist/*
python -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  monl-compiler==0.9.0-beta.10
python -m twine upload dist/*
```
A first release goes to TestPyPI. After the test installation, run the proof
workflow outside the repository: `monl --version`, `monl --help`, compilation
of a specification without assets, backend startup and requests, then
`monl-platform` on `/health`, `/ready` and `/favicon.ico`. The second release
goes to PyPI and must happen only after this validation. Neither of these two
actual releases is performed by the repository's test suite.

A successful publication can then be checked without authentication with:

```bash
python -m pip index versions monl-compiler
```
