"""Test event handler of new_account_support_case.

Neither LocalStack nor moto_server support the "support" service,
so testing is very minimal.
"""
import os
import uuid

import pytest
import boto3
from moto import mock_iam
from moto import mock_support
from moto.core import ACCOUNT_ID

import new_account_support_case as lambda_func

AWS_REGION = os.getenv("AWS_REGION", default="aws-global")


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
def aws_credentials(tmpdir):
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
    os.environ["AWS_SHARED_CREDENTIALS_FILE"] = str(path)

    # Ensure that any existing environment variables are overridden with
    # 'mock' values.
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_PROFILE"] = "testing"  # Not standard, but in use locally.


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
def monkeypatch_get_account_id(monkeypatch):
    """Mock get_account_id() to return a fake account ID."""

    def mock_get_account_id(event):  # pylint: disable=unused-argument
        return ACCOUNT_ID

    monkeypatch.setattr(lambda_func, "get_account_id", mock_get_account_id)


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


def test_lambda_handler_missing_company_name(lambda_context):
    """Invoke the lambda handler with no company name."""
    os.environ["COMPANY_NAME"] = ""
    os.environ["CC_LIST"] = "foo.com"
    with pytest.raises(lambda_func.SupportCaseInvalidArgumentsError) as exc:
        lambda_func.lambda_handler("mocked_event", lambda_context)
    assert (
        "Environment variable 'COMPANY_NAME' must provide the name of the "
        "company requesting new account"
    ) in str(exc.value)


def test_lambda_handler_missing_cc_list(lambda_context):
    """Invoke the lambda handler with no CC List."""
    os.environ["COMPANY_NAME"] = "TEST CASE--Please ignore"
    os.environ["CC_LIST"] = ""
    with pytest.raises(lambda_func.SupportCaseInvalidArgumentsError) as exc:
        lambda_func.lambda_handler("mocked_event", lambda_context)
    assert (
        "Environment variable 'CC_LIST' must provide at least one email "
        "address to CC on this case"
    ) in str(exc.value)


def test_lambda_handler_valid_arguments(
    lambda_context,
    iam_client,
    support_client,
    monkeypatch_get_account_id,
):
    """Invoke the lambda handler with only valid arguments."""
    # Generate some random string for the company name,
    company_name = str(uuid.uuid4())
    cc_list = "bar.com"

    os.environ["COMPANY_NAME"] = company_name
    os.environ["CC_LIST"] = cc_list
    # The lambda function doesn't return anything, but will generate
    # an exception for failure.  So returning nothing is considered success.
    assert not lambda_func.lambda_handler("mocked_event", lambda_context)

    cases = support_client.describe_cases()
    for case in cases["cases"]:
        if company_name in case["subject"] and case["ccEmailAddresses"][0] == cc_list:
            break
    else:
        assert False
