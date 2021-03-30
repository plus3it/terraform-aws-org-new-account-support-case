"""Test event handler of new_account_support_case.

Neither LocalStack nor moto_server support the "support" service,
so testing is very minimal.
"""
import os
import uuid

import pytest
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
