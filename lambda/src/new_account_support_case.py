#!/usr/bin/env python3
"""Enable Enterprise support on a new account."""
from argparse import ArgumentParser, RawDescriptionHelpFormatter
import os
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

    org = boto3.client("organizations")
    while True:
        account_status = org.describe_create_account_status(
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


def main(new_account_id, company_name, cc_list):
    """Create an Enterprise support case and extract the display ID."""
    # Prepare some of the fields needed for the create_case() call.
    case_subject = (
        f"Add new account to {company_name} Enterprise support: {new_account_id}"
    )
    case_communication_body = (
        f"Hi AWS, please add this account to Enterprise support and add tax "
        f"exemption (see the Tax Exemption letter under the payer account): "
        f"{new_account_id}"
    )

    # Create the Enterprise support case.
    client = boto3.client("support")
    try:
        response = client.create_case(
            subject=case_subject,
            severityCode="low",
            categoryCode="other-account-issues",
            serviceCode="customer-account",
            communicationBody=case_communication_body,
            ccEmailAddresses=[cc_list],
            language="en",
            issueType="customer-service",
        )
    except botocore.exceptions.ClientError as err:
        raise SupportCaseError(err) from err

    # Extract case ID from response.
    case_id = response["caseId"]
    if not case_id:
        raise SupportCaseError("Missing case_id in create_case() response")

    # Use the case ID to obtain further details from the case and in
    # particular, the display ID.
    try:
        case = client.describe_cases(caseIdList=[case_id])
    except botocore.exceptions.ClientError as err:
        raise SupportCaseError(err) from err

    try:
        display_id = case["cases"][0]["displayId"]
    except KeyError:
        raise SupportCaseError(err) from err

    LOG.info(f"Case {display_id} opened")
    return 0


@LOG.inject_lambda_context(log_event=True)
def lambda_handler(event, context):  # pylint: disable=unused-argument
    """Entry point if script called by AWS Lamdba."""
    # Required:  Name of company requesting new account.
    company_name = os.environ.get("COMPANY_NAME")

    # Required:  Comma-separated list of email addresses to CC on this case.
    cc_list = os.environ.get("CC_LIST")

    LOG.info({"COMPANY_NAME": company_name, "CC_LIST": cc_list})

    # Check for missing requirement environment variables.
    if not company_name:
        msg = (
            "Environment variable 'COMPANY_NAME' must provide "
            "the name of the company requesting new account."
        )
        LOG.error(msg)
        raise SupportCaseInvalidArgumentsError(msg)

    if not cc_list:
        msg = (
            "Environment variable 'CC_LIST' must provide at least one "
            "email address to CC on this case."
        )
        LOG.error(msg)
        raise SupportCaseInvalidArgumentsError(msg)

    try:
        account_id = get_account_id(event)
    except AccountCreationFailedError as account_err:
        LOG.error({"failure": account_err})
        raise
    except Exception:
        LOG.exception("Unexpected, unknown exception in account ID logic")
        raise

    try:
        main(account_id, company_name, cc_list)
    except SupportCaseInvalidArgumentsError as err:
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

        required_args = parser.add_argument_group("required named arguments")
        required_args.add_argument(
            "--company_name",
            required=True,
            type=str,
            help="Name of company requesting new account.",
        )
        required_args.add_argument(
            "--cc_list",
            required=True,
            type=str,
            help=(
                "Comma-separate list of email address to CC on this case.  At"
                "least one email address is required."
            ),
        )
        required_args.add_argument(
            "--new_account_id",
            required=True,
            type=str,
            help="Account ID for account being added to Enterprise support.",
        )
        return parser.parse_args()

    sys.exit(main(**vars(create_args())))
