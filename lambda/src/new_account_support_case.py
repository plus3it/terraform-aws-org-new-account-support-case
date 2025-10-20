#!/usr/bin/env python3
"""Enable Enterprise support on a new account."""
from argparse import ArgumentParser, RawDescriptionHelpFormatter
import os
from string import Template
import sys

from aws_lambda_powertools import Logger
import boto3


LOG_LEVEL = os.environ.get("LOG_LEVEL", "info")

# BOTO_LOG_LEVEL_MAPPING = {"debug": 10, "info": 20, "warning": 30, "error": 40}
# boto3.set_stream_logger("botocore", BOTO_LOG_LEVEL_MAPPING[LOG_LEVEL])

LOG = Logger(
    service="new_account_support_case",
    level=LOG_LEVEL,
    stream=sys.stderr,
    location="%(name)s.%(funcName)s:%(lineno)d",
    timestamp="%(asctime)s.%(msecs)03dZ",
    datefmt="%Y-%m-%dT%H:%M:%S",
)


MOCKSTACK_HOST = os.getenv("LOCALSTACK_HOST") or os.getenv("MOTO_HOST")
MOCKSTACK_ENDPOINT = f"http://{MOCKSTACK_HOST}:4615" if MOCKSTACK_HOST else None


### Classes and functions specific to the Lambda event handler itself.


def exception_hook(exc_type, exc_value, exc_traceback):
    """Log all exceptions with hook for sys.excepthook."""
    LOG.exception(
        "%s: %s",
        exc_type.__name__,
        exc_value,
        exc_info=(exc_type, exc_value, exc_traceback),
    )


def get_new_account_id(event):
    """Return account id for new account events."""
    return event["detail"]["serviceEventDetails"]["createAccountStatus"]["accountId"]


def get_invite_account_id(event):
    """Return account id for invite account events."""
    return event["detail"]["requestParameters"]["target"]["id"]


def get_account_id(event):
    """Return account id for supported events."""
    event_name = event["detail"]["eventName"]
    get_account_id_strategy = {
        "CreateAccountResult": get_new_account_id,
        "InviteAccountToOrganization": get_invite_account_id,
    }
    return get_account_id_strategy[event_name](event)


### Classes and functions specific to creating the support case.


class SupportCaseInvalidArgumentsError(Exception):
    """Invalid arguments were used to create a support case."""


class SupportCaseError(Exception):
    """Error creating or extracting details for support case."""


def template_to_string(template, account_id):
    """Replace account_id variable in string with actual value."""
    return Template(template).substitute(account_id=account_id)


def main(account_id, cc_list, subject, communication_body):
    """Create an Enterprise support case and extract the display ID."""
    subject = template_to_string(subject, account_id)
    communication_body = template_to_string(communication_body, account_id)

    # Create the Enterprise support case.
    support_client = boto3.client("support", endpoint_url=MOCKSTACK_ENDPOINT)
    response = support_client.create_case(
        subject=subject,
        severityCode="low",
        categoryCode="other-account-issues",
        serviceCode="customer-account",
        communicationBody=communication_body,
        ccEmailAddresses=[cc_list],
        language="en",
        issueType="customer-service",
    )

    # Extract case ID from response.
    case_id = response["caseId"]
    if not case_id:
        raise SupportCaseError("Missing case_id in create_case() response")

    # Use the case ID to obtain further details from the case and in
    # particular, the display ID.
    case = support_client.describe_cases(caseIdList=[case_id])

    display_id = case["cases"][0]["displayId"]

    LOG.info({"comment": "Case %s opened"}, display_id)


def check_for_null_envvars(cc_list, communication_body, subject):
    """Check for missing requirement environment variables."""
    if not cc_list:
        msg = (
            "Environment variable 'CC_LIST' must provide at least one "
            "email address to CC on this case."
        )
        LOG.error(msg)
        raise SupportCaseInvalidArgumentsError(msg)

    if not subject:
        msg = (
            "Environment variable 'SUBJECT' must provide the 'Subject' text "
            "for the communication sent to support."
        )
        LOG.error(msg)
        raise SupportCaseInvalidArgumentsError(msg)

    if not communication_body:
        msg = (
            "Environment variable 'COMMUNICATION_BODY' must provide the "
            "body of the communication sent to support."
        )
        LOG.error(msg)
        raise SupportCaseInvalidArgumentsError(msg)


@LOG.inject_lambda_context(log_event=True)
def lambda_handler(event, context):  # pylint: disable=unused-argument
    """Entry point if script called by AWS Lamdba."""
    cc_list = os.environ.get("CC_LIST")
    communication_body = os.environ.get("COMMUNICATION_BODY")
    subject = os.environ.get("SUBJECT")
    LOG.info(
        {
            "CC_LIST": cc_list,
            "COMMUNICATION_BODY": communication_body,
            "SUBJECT": subject,
            "MOCKSTACK_ENDPOINT": MOCKSTACK_ENDPOINT,
        }
    )

    # Check for missing requirement environment variables.
    check_for_null_envvars(cc_list, communication_body, subject)

    account_id = get_account_id(event)

    main(account_id, cc_list, subject, communication_body)


# Configure exception handler
sys.excepthook = exception_hook

if __name__ == "__main__":

    def create_args():
        """Return parsed arguments."""
        parser = ArgumentParser(
            formatter_class=RawDescriptionHelpFormatter,
            description="""
Enable Enterprise support for a new account.

NOTE:  Use the environment variable 'LOG_LEVEL' to set the desired log level
('error', 'warning', 'info' or 'debug').  The default level is 'info'.""",
        )
        parser.add_argument(
            "--subject",
            required=True,
            type=str,
            help="Text for 'Subject' field of the communication sent to support.",
        )
        parser.add_argument(
            "--communication_body",
            required=True,
            type=str,
            help="Text for body of the communication sent to support.",
        )
        parser.add_argument(
            "--cc_list",
            required=True,
            type=str,
            help=(
                "Comma-separate list of email address to CC on this case.  At"
                "least one email address is required."
            ),
        )
        parser.add_argument(
            "--account_id",
            required=True,
            type=str,
            help="Account ID for account being added to Enterprise support.",
        )
        return parser.parse_args()

    sys.exit(main(**vars(create_args())))
