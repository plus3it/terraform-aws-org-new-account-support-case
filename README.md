# terraform-aws-org-new-account-support-case

A Terraform module to enable Enterprise support on a new account.

This module uses CloudWatch Events to identify when new accounts are
added or invited to an AWS Organization, and triggers a Lambda function
to create the new account.

## Testing

To set up and run tests against the Terraform configuration:

```
# Start up LocalStack, a mock AWS stack:
make localstack/up

# Run the tests:
make terraform/pytest

# Shut down LocalStack and clean up docker images:
make localstack/clean
```

<!-- BEGIN TFDOCS -->
## Requirements

| Name | Version |
|------|---------|
| terraform | >= 0.12 |

## Providers

| Name | Version |
|------|---------|
| aws | n/a |
| random | n/a |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| cc\_list | Comma-separated list of email addresses to CC on this case.  At least one email address is required. | `string` | n/a | yes |
| company\_name | Name of company requesting Enterprise Support of a new account. | `string` | n/a | yes |
| log\_level | Log level of the lambda output, one of: debug, info, warning, error, critical | `string` | `"info"` | no |

## Outputs

| Name | Description |
|------|-------------|
| aws\_cloudwatch\_event\_rule | The cloudwatch event rule object |
| aws\_cloudwatch\_event\_target | The cloudWatch event target object |
| aws\_lambda\_permission\_events | The lambda permission object for cloudwatch event triggers |
| lambda | The lambda module object |

<!-- END TFDOCS -->
