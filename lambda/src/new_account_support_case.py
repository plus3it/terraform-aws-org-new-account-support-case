#!/usr/bin/env python3
"""Enable Enterprise support on a new account."""
from argparse import ArgumentParser, RawDescriptionHelpFormatter
import os
from string import Template
import sys
import time

from aws_lambda_powertools import Logger
import boto3
import botocore


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

LOCALSTACK_IP = os.getenv("LOCALSTACK_HOSTNAME")
ORG_ENDPOINT = "http://localstack:4615" if LOCALSTACK_IP else None
EDGE_ENDPOINT = "http://localstack:4566" if LOCALSTACK_IP else None


### Classes and functions specific to the Lambda event handler itself.


class AccountCreationFailedError(Exception):
    """Account creation failed."""


def get_new_account_id(event):
    """Return account id for new account events."""
    create_account_status_id = (
        event["detail"]
        .get("responseElements", {})
        .get("createAccountStatus", {})["id"]  # fmt: no
    )
    LOG.info({"create_account_status_id": create_account_status_id})

    org_client = boto3.client("organizations", endpoint_url=ORG_ENDPOINT)
    while True:
        account_status = org_client.describe_create_account_status(
            CreateAccountRequestId=create_account_status_id
        )
        state = account_status["CreateAccountStatus"]["State"].upper()
        if state == "SUCCEEDED":
            return account_status["CreateAccountStatus"]["AccountId"]
        if state == "FAILED":
            LOG.error({"create_account_status_failure": account_status})
            raise AccountCreationFailedError
        LOG.info({"create_account_status_state": state})
        time.sleep(5)


def get_invite_account_id(event):
    """Return account id for invite account events."""
    return event["detail"]["requestParameters"]["target"]["id"]


def get_account_id(event):
    """Return account id for supported events."""
    event_name = event["detail"]["eventName"]
    get_account_id_strategy = {
        "CreateAccount": get_new_account_id,
        "CreateGovCloudAccount": get_new_account_id,
        "InviteAccountToOrganization": get_invite_account_id,
    }
    try:
        account_id = get_account_id_strategy[event_name](event)
    except (botocore.exceptions.ClientError, AccountCreationFailedError) as err:
        raise AccountCreationFailedError(err) from err
    return account_id


### Classes and functions specific to creating the support case.


class SupportCaseInvalidArgumentsError(Exception):
    """Invalid arguments were used to create a support case."""


class SupportCaseError(Exception):
    """Error creating or extracting details for support case."""


def template_to_string(template, account_id):
    """Replace account_id variable in string with actual value."""
    try:
        return Template(template).substitute(account_id=account_id)
    except KeyError as err:
        raise SupportCaseError(
            f"Unexpected variable {err} found in '{template}'"
        ) from err
    return template


def main(account_id, cc_list, subject, communication_body):
    """Create an Enterprise support case and extract the display ID."""
    subject = template_to_string(subject, account_id)
    communication_body = template_to_string(communication_body, account_id)

    # Create the Enterprise support case.
    support_client = boto3.client("support", endpoint_url=EDGE_ENDPOINT)
    try:
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
    except botocore.exceptions.ClientError as create_case_err:
        raise SupportCaseError(create_case_err) from create_case_err

    # Extract case ID from response.
    case_id = response["caseId"]
    if not case_id:
        raise SupportCaseError("Missing case_id in create_case() response")

    # Use the case ID to obtain further details from the case and in
    # particular, the display ID.
    try:
        case = support_client.describe_cases(caseIdList=[case_id])
    except botocore.exceptions.ClientError as describe_case_err:
        raise SupportCaseError(describe_case_err) from describe_case_err

    try:
        display_id = case["cases"][0]["displayId"]
    except KeyError as key_err:
        raise SupportCaseError(key_err) from key_err

    LOG.info(f"Case {display_id} opened")
    return 0


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
        }
    )

    # Check for missing requirement environment variables.
    check_for_null_envvars(cc_list, communication_body, subject)

    try:
        account_id = get_account_id(event)
    except AccountCreationFailedError as account_err:
        LOG.error({"failure": account_err})
        raise
    except Exception:
        LOG.exception("Unexpected, unknown exception in account ID logic")
        raise

    try:
        main(account_id, cc_list, subject, communication_body)
    except (SupportCaseInvalidArgumentsError, SupportCaseError) as err:
        LOG.error({"failure": err})
        raise
    except Exception:
        LOG.exception("Unexpected, unknown exception creating support case")
        raise


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
