"""Test Terraform installation of new_account_support_case.

Verifies the Terraform configuration by:
    - verifying the init/plan and apply are successful,
    - verifying the Terraform output,
    - verifying a "dry run" of the lambda is successful,
    - executing the lambda to verify the libraries are installed.
"""
from datetime import datetime
import json
import os
from pathlib import Path
import uuid

import pytest
import tftest

import boto3
import localstack_client.session
from moto import mock_organizations


AWS_DEFAULT_REGION = os.getenv("AWS_REGION", default="us-east-1")

# The AWS organizations service is not provided with the free version of
# LocalStack, but moto does support it.
ORG_ENDPOINT = "http://localhost:4615"

MOCK_ORG_NAME = "test_account"
MOCK_ORG_EMAIL = f"{MOCK_ORG_NAME}@mock.org"


@pytest.fixture(scope="module")
def config_path():
    """Find the location of 'main.tf' in current dir or a parent dir."""
    current_dir = Path.cwd()
    if list(Path(current_dir).glob("*.tf")):
        return str(current_dir)

    # Recurse upwards until the Terraform config file is found.
    for parent in current_dir.parents:
        if list(Path(parent).glob("*.tf")):
            return str(parent)

    pytest.exit(msg="Unable to find Terraform config file 'main.tf", returncode=1)
    return ""  # Will never reach this point, but satisfies pylint.


@pytest.fixture(scope="module")
def localstack_session():
    """Return a LocalStack client session."""
    return localstack_client.session.Session()


@pytest.fixture(scope="function")
def aws_credentials(tmpdir, monkeypatch):
    """Create mocked AWS credentials for moto."""
    # Create a temporary AWS credentials file for calls to boto.Session().
    aws_creds = [
        "[testing]",
        "aws_access_key_id = testing",
        "aws_secret_access_key = testing",
    ]
    path = tmpdir.join("aws_test_creds")
    path.write("\n".join(aws_creds))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(path))

    # Ensure that any existing environment variables are overridden with
    # 'mock' values.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_PROFILE", "testing")  # Not standard, but in use locally.


@pytest.fixture(scope="function")
def org_client(aws_credentials):
    """Yield a mock organization that will not affect a real AWS account."""
    with mock_organizations():
        yield boto3.client("organizations", endpoint_url=ORG_ENDPOINT)


@pytest.fixture(scope="function")
def mock_event(org_client):
    """Create an event used as an argument to the Lambda handler."""
    org_client.create_organization(FeatureSet="ALL")
    account_id = org_client.create_account(
        AccountName=MOCK_ORG_NAME, Email=MOCK_ORG_EMAIL
    )["CreateAccountStatus"]["Id"]
    return {
        "version": "0",
        "id": str(uuid.uuid4()),
        "detail-type": "AWS API Call via CloudTrail",
        "source": "aws.organizations",
        "account": "222222222222",
        "time": datetime.now().isoformat(),
        "region": AWS_DEFAULT_REGION,
        "resources": [],
        "detail": {
            "eventName": "CreateAccount",
            "eventSource": "organizations.amazonaws.com",
            "responseElements": {
                "createAccountStatus": {
                    "id": account_id,
                }
            },
        },
    }


@pytest.fixture(scope="module")
def tf_output(config_path):
    """Return the output after applying the Terraform configuration.

    Note:  the scope for this pytest fixture is "module", so this will only
    run once for this file.
    """
    # Terraform requires that AWS_DEFAULT_REGION be set.  If this script is
    # invoked from the command line in a properly setup environment, that
    # environment variable is set, but not if invoked from a Makefile.
    os.environ["AWS_DEFAULT_REGION"] = AWS_DEFAULT_REGION

    tf_test = tftest.TerraformTest(config_path, basedir=None, env=None)

    # Use LocalStack to simulate the AWS stack.  "localstack.tf" contains
    # the endpoints and services information needed by LocalStack.
    tf_test.setup(extra_files=[str(Path(Path.cwd() / "tests" / "localstack.tf"))])

    tf_vars = {
        "cc_list": "foo.com,bar.com",
        "subject": "Add a new account for Acme",
        "communication_body": "Please add this account to Enterprise support",
    }

    try:
        tf_test.apply(tf_vars=tf_vars)
        yield tf_test.output(json_format=True)
    except tftest.TerraformTestError as exc:
        pytest.exit(
            msg=f"Catastropic error running Terraform 'apply':  {exc}", returncode=1
        )
    finally:
        tf_test.destroy(tf_vars=tf_vars)


def test_outputs(tf_output):
    """Verify outputs of Terraform installation."""
    keys = [*tf_output]
    assert keys == [
        "aws_cloudwatch_event_rule",
        "aws_cloudwatch_event_target",
        "aws_lambda_permission_events",
        "lambda",
    ]

    prefix = "new_account_support_case"

    lambda_module = tf_output["lambda"]
    assert lambda_module["function_name"].startswith(prefix)

    event_rule_output = tf_output["aws_cloudwatch_event_rule"]
    assert event_rule_output["name"].startswith(prefix)

    event_target_output = tf_output["aws_cloudwatch_event_target"]
    assert event_target_output["rule"].startswith(prefix)

    permission_events_output = tf_output["aws_lambda_permission_events"]
    assert permission_events_output["function_name"].startswith(prefix)


def test_lambda_dry_run(tf_output, localstack_session):
    """Verify a dry run of the lambda is successful."""
    lambda_client = localstack_session.client("lambda", region_name=AWS_DEFAULT_REGION)
    lambda_module = tf_output["lambda"]
    response = lambda_client.invoke(
        FunctionName=lambda_module["function_name"],
        InvocationType="DryRun",
    )
    assert response["StatusCode"] == 204


def test_lambda_invocation(tf_output, localstack_session, mock_event):
    """Verify a support case was created."""
    lambda_client = localstack_session.client("lambda", region_name=AWS_DEFAULT_REGION)
    lambda_module = tf_output["lambda"]
    response = lambda_client.invoke(
        FunctionName=lambda_module["function_name"],
        InvocationType="RequestResponse",
        Payload=json.dumps(mock_event),
    )
    assert response["StatusCode"] == 200

    # No response is a good response.  The Lambda is not expected to
    # return anything.
    response_payload = json.loads(response["Payload"].read().decode())
    assert not response_payload

    support_client = localstack_session.client("support")
    all_cases = support_client.describe_cases()
    assert all_cases

    for case in all_cases["cases"]:
        if case["subject"] != "Add a new account for Acme":
            continue
        if case["ccEmailAddresses"][0] != "foo.com,bar.com":
            continue
        if case["recentCommunications"]["communications"][0]["body"] == (
            "Please add this account to Enterprise support"
        ):
            break
    else:
        assert False, "Failed to find the support case the Lambda created"
