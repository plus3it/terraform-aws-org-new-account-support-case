"""Test event handler of new_account_support_case.

Neither LocalStack nor moto_server support the "support" service,
so testing is very minimal.
"""
from datetime import datetime
import os
import uuid

import pytest
import boto3
from moto import mock_iam
from moto import mock_support
from moto import mock_organizations
from moto.core import ACCOUNT_ID

import new_account_support_case as lambda_func

AWS_REGION = os.getenv("AWS_REGION", default="aws-global")
MOCK_ORG_NAME = "test_account"
MOCK_ORG_EMAIL = f"{MOCK_ORG_NAME}@mock.org"


@pytest.fixture
def lambda_context():
    """Create mocked lambda context injected by the powertools logger."""

    class LambdaContext:  # pylint: disable=too-few-public-methods
        """Mock lambda context."""

        def __init__(self):
            """Initialize context variables."""
            self.function_name = "test"
            self.memory_limit_in_mb = 128
            self.invoked_function_arn = (
                f"arn:aws:lambda:{AWS_REGION}:{ACCOUNT_ID}:function:test"
            )
            self.aws_request_id = str(uuid.uuid4())

    return LambdaContext()


@pytest.fixture(scope="function")
def aws_credentials(tmpdir, monkeypatch):
    """Create mocked AWS credentials for moto.

    In addition to using the aws_credentials fixture, the test functions
    must also use a mocked client.  For this test file, that would be the
    test fixture "iam_client", which invokes "mock_iam()".
    """
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
def iam_client(aws_credentials):
    """Yield a mock IAM client that will not affect a real AWS account."""
    with mock_iam():
        yield boto3.client("iam", region_name=AWS_REGION)


@pytest.fixture(scope="function")
def support_client(aws_credentials):
    """Yield a mock support client that will not affect a real AWS account."""
    with mock_support():
        yield boto3.client("support", region_name=AWS_REGION)


@pytest.fixture(scope="function")
def org_client(aws_credentials):
    """Yield a mock organization that will not affect a real AWS account."""
    with mock_organizations():
        yield boto3.client("organizations", region_name=AWS_REGION)


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
        "region": "us-east-1",
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


def test_main_func_valid_arguments(support_client):
    """Test use of valid arguments for main()."""
    # Generate some random string for the company name,
    company_name = str(uuid.uuid4())
    cc_list = "foo.com, foobar.com"

    return_code = lambda_func.main(
        new_account_id=ACCOUNT_ID,
        company_name=company_name,
        cc_list=cc_list,
    )
    assert return_code == 0

    cases = support_client.describe_cases()
    for case in cases["cases"]:
        if company_name in case["subject"] and case["ccEmailAddresses"][0] == cc_list:
            break
    else:
        assert False


def test_lambda_handler_missing_company_name(lambda_context, monkeypatch):
    """Invoke the lambda handler with no company name."""
    monkeypatch.delenv("COMPANY_NAME", raising=False)
    monkeypatch.setenv("CC_LIST", "foo.com")
    with pytest.raises(lambda_func.SupportCaseInvalidArgumentsError) as exc:
        lambda_func.lambda_handler("mocked_event", lambda_context)
    assert (
        "Environment variable 'COMPANY_NAME' must provide the name of the "
        "company requesting new account"
    ) in str(exc.value)


def test_lambda_handler_missing_cc_list(lambda_context, monkeypatch):
    """Invoke the lambda handler with no CC List."""
    monkeypatch.setenv("COMPANY_NAME", "TEST CASE--Please ignore")
    monkeypatch.delenv("CC_LIST", raising=False)
    with pytest.raises(lambda_func.SupportCaseInvalidArgumentsError) as exc:
        lambda_func.lambda_handler("mocked_event", lambda_context)
    assert (
        "Environment variable 'CC_LIST' must provide at least one email "
        "address to CC on this case"
    ) in str(exc.value)


def test_lambda_handler_valid_arguments(
    lambda_context, iam_client, support_client, monkeypatch, mock_event
):
    """Invoke the lambda handler with only valid arguments."""
    # Generate some random string for the company name,
    company_name = str(uuid.uuid4())
    cc_list = "bar.com"

    monkeypatch.setenv("COMPANY_NAME", company_name)
    monkeypatch.setenv("CC_LIST", cc_list)
    # The lambda function doesn't return anything, but will generate
    # an exception for failure.  So returning nothing is considered success.
    assert not lambda_func.lambda_handler(mock_event, lambda_context)

    cases = support_client.describe_cases()
    for case in cases["cases"]:
        if company_name in case["subject"] and case["ccEmailAddresses"][0] == cc_list:
            break
    else:
        assert False
