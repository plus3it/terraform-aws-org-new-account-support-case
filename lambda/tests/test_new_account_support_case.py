"""Test event handler of new_account_support_case.

Neither LocalStack nor moto_server support the "support" service,
so testing is very minimal.
"""

from datetime import datetime
import os
import uuid

import boto3
import pytest
from moto import mock_iam
from moto import mock_support
from moto import mock_organizations
from moto.core import DEFAULT_ACCOUNT_ID as ACCOUNT_ID

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
    car_id = org_client.create_account(AccountName=MOCK_ORG_NAME, Email=MOCK_ORG_EMAIL)[
        "CreateAccountStatus"
    ]["Id"]
    create_account_status = org_client.describe_create_account_status(
        CreateAccountRequestId=car_id
    )
    return {
        "version": "0",
        "id": str(uuid.uuid4()),
        "detail-type": "AWS Service Event via CloudTrail",
        "source": "aws.organizations",
        "account": ACCOUNT_ID,
        "time": datetime.now().isoformat(),
        "region": AWS_REGION,
        "resources": [],
        "detail": {
            "eventName": "CreateAccountResult",
            "eventSource": "organizations.amazonaws.com",
            "serviceEventDetails": {
                "createAccountStatus": {
                    "accountId": create_account_status["CreateAccountStatus"][
                        "AccountId"
                    ]
                }
            },
        },
    }


@pytest.fixture(scope="function")
def account_id(org_client, mock_event):
    """Return the account_id created for the new account in the org."""
    return mock_event["detail"]["serviceEventDetails"]["createAccountStatus"][
        "accountId"
    ]


def test_main_func_valid_arguments(support_client):
    """Test use of valid arguments for main()."""
    cc_list = "foo.com, foobar.com"
    subject = str(uuid.uuid4())
    communication_body = str(uuid.uuid4())

    lambda_func.main(
        account_id=ACCOUNT_ID,
        cc_list=cc_list,
        subject=subject,
        communication_body=communication_body,
    )

    cases = support_client.describe_cases()
    for case in cases["cases"]:
        if (
            subject == case["subject"]
            and cc_list == case["ccEmailAddresses"][0]
            and communication_body
            == case["recentCommunications"]["communications"][0]["body"]
        ):
            break
    else:
        assert False


def test_lambda_handler_missing_cc_list(lambda_context, monkeypatch, mock_event):
    """Invoke the lambda handler with no CC List."""
    monkeypatch.delenv("CC_LIST", raising=False)
    monkeypatch.setenv("SUBJECT", "TEST CASE--Please ignore")
    monkeypatch.setenv("COMMUNICATION_BODY", "Please support this account.")
    with pytest.raises(lambda_func.SupportCaseInvalidArgumentsError) as exc:
        lambda_func.lambda_handler(mock_event, lambda_context)
    assert (
        "Environment variable 'CC_LIST' must provide at least one email "
        "address to CC on this case"
    ) in str(exc.value)


def test_lambda_handler_missing_subject(lambda_context, monkeypatch, mock_event):
    """Invoke the lambda handler with no subject."""
    monkeypatch.setenv("CC_LIST", "foo.com")
    monkeypatch.delenv("SUBJECT", raising=False)
    monkeypatch.setenv("COMMUNICATION_BODY", "Please support this account.")
    with pytest.raises(lambda_func.SupportCaseInvalidArgumentsError) as exc:
        lambda_func.lambda_handler(mock_event, lambda_context)
    assert (
        "Environment variable 'SUBJECT' must provide the 'Subject' text for "
        "the communication sent to support"
    ) in str(exc.value)


def test_lambda_handler_missing_communication_body(
    lambda_context, monkeypatch, mock_event
):
    """Invoke the lambda handler with no subject."""
    monkeypatch.setenv("CC_LIST", "foo.com")
    monkeypatch.setenv("SUBJECT", "TEST CASE--Please ignore")
    monkeypatch.delenv("COMMUNICATION_BODY", raising=False)
    with pytest.raises(lambda_func.SupportCaseInvalidArgumentsError) as exc:
        lambda_func.lambda_handler(mock_event, lambda_context)
    assert (
        "Environment variable 'COMMUNICATION_BODY' must provide the body of "
        "the communication sent to support"
    ) in str(exc.value)


def test_lambda_handler_valid_arguments(
    lambda_context, iam_client, support_client, monkeypatch, mock_event
):
    """Invoke the lambda handler with only valid arguments."""
    cc_list = "bar.com"
    subject = str(uuid.uuid4())
    communication_body = str(uuid.uuid4())

    monkeypatch.setenv("CC_LIST", cc_list)
    monkeypatch.setenv("SUBJECT", subject)
    monkeypatch.setenv("COMMUNICATION_BODY", communication_body)
    # The lambda function doesn't return anything, but will generate
    # an exception for failure.  So returning nothing is considered success.
    assert not lambda_func.lambda_handler(mock_event, lambda_context)

    cases = support_client.describe_cases()
    for case in cases["cases"]:
        if (
            subject == case["subject"]
            and cc_list == case["ccEmailAddresses"][0]
            and communication_body
            == case["recentCommunications"]["communications"][0]["body"]
        ):
            break
    else:
        assert False


def test_lambda_handler_envvars_with_account_id(
    lambda_context,
    iam_client,
    support_client,
    monkeypatch,
    mock_event,
    account_id,
):  # pylint: disable=too-many-arguments
    """Invoke the lambda handler with account_id variable in envvars."""
    wild_card = str(uuid.uuid4())

    monkeypatch.setenv("CC_LIST", "bar.com")
    monkeypatch.setenv("SUBJECT", f"{wild_card} with $account_id")
    monkeypatch.setenv(
        "COMMUNICATION_BODY", f"Email body {wild_card} with ${{account_id}}"
    )
    assert not lambda_func.lambda_handler(mock_event, lambda_context)

    cases = support_client.describe_cases()
    for case in cases["cases"]:
        if (
            case["subject"] == f"{wild_card} with {account_id}"
            and case["recentCommunications"]["communications"][0]["body"]
            == f"Email body {wild_card} with {account_id}"
        ):
            break
    else:
        assert False


def test_lambda_handler_envvars_with_bad_vars(
    lambda_context,
    iam_client,
    support_client,
    monkeypatch,
    mock_event,
    account_id,
):  # pylint: disable=too-many-arguments
    """Invoke the lambda handler with account_id variable in envvars."""
    test_subject = "Subject with $unknown_var"
    monkeypatch.setenv("CC_LIST", "bar.com")
    monkeypatch.setenv("SUBJECT", test_subject)
    monkeypatch.setenv("COMMUNICATION_BODY", "Email body")
    with pytest.raises(KeyError) as exc:
        lambda_func.lambda_handler(mock_event, lambda_context)
        assert f"Unexpected variable 'unknown_var' found in '{test_subject}'" in str(
            exc.value
        )

    test_body = "Email body with $account_id and $unexpected_var"
    monkeypatch.setenv("CC_LIST", "bar.com")
    monkeypatch.setenv("SUBJECT", "Test subject")
    monkeypatch.setenv("COMMUNICATION_BODY", test_body)
    with pytest.raises(KeyError) as exc:
        lambda_func.lambda_handler(mock_event, lambda_context)
        assert f"Unexpected variable 'unexpected_var' found in '{test_body}'" in str(
            exc.value
        )
