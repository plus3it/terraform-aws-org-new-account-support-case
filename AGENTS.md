# Agent Instructions

Before starting any task in this repository:

1. Run `make agents/sync`. It writes the shared Plus3 IT instructions for this repository's tardigrade-ci version to `.agents/plus3it/AGENTS.md`.
2. Read `.agents/plus3it/AGENTS.md` and follow it together with this file. If the sync fails, tell the user, and don't guess the conventions.

These rules always apply, even without the shared instructions:

- Don't push, open pull requests, publish releases, or apply infrastructure changes unless the user asks. List those steps for a person in your final report.
- Don't edit files under `.agents/plus3it/`; they are generated and overwritten by the sync.

@.agents/plus3it/AGENTS.md

## Repository-specific

### Purpose

This Terraform module creates a Python Lambda function that opens an AWS Support case for each new account in an AWS Organization. EventBridge rules for the `CreateAccountResult` and `InviteAccountToOrganization` events trigger the function, and `event_types` selects which of the two rules are created. The required inputs are `cc_list`, `subject`, and `communication_body`, and the `lambda` object passes extra settings to the upstream Lambda module. It outputs `lambda`, `aws_cloudwatch_event_rule`, `aws_cloudwatch_event_target`, and `aws_lambda_permission_events`.

### Module-specific files

- `lambda/src/` — Source of the Lambda function (`new_account_support_case.py`), packaged by the module; `requirements.txt` lists its runtime packages
- `lambda/tests/` — Python unit tests for the Lambda function
- `requirements/` — Test packages: `requirements_common.txt` (shared by the other two), `requirements_dev.txt`, and `requirements_test.txt`
- `Dockerfile` and `Dockerfile_test` — Images based on the tardigrade-ci image; `Dockerfile` installs the Lambda and test requirements, and `Dockerfile_test` installs only `requirements_test.txt`

### Deviations from the terraform-module profile

- The Makefile exports `PYTHONPATH` with `./lambda/src` appended, so Python tools can import the Lambda source.
- `make python/deps` installs `lambda/src/requirements.txt`. `make pytest/deps` installs `requirements_dev.txt` and `requirements_test.txt` from `requirements/`.
- The Python unit tests run separately from the mockstack tests. `test.yml` has a `unit-test` job that runs `make docker/run target=pytest/lambda/tests`. This runs `pytest lambda/tests` in the image built from `Dockerfile`, using the tardigrade-ci `pytest/%` target. This job is in addition to the shared `test` job.
- The shared `test` job in `test.yml` runs the standard mockstack Terraform tests (`make mockstack/up`, `make mockstack/pytest`, `make mockstack/clean`).
- `make mockstack/pytest/lambda` is a custom variant of `mockstack/pytest`. It runs `terraform/pytest` in a container built from `Dockerfile_test` (image `new-account-support-case-integration-test:latest`) on the `terraform_pytest_default` network with `LOCALSTACK_HOST=localstack`. CI does not use it; the `README.md` lists it as a local step after `make mockstack/up`.
