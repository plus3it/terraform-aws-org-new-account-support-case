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
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 0.12 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_aws"></a> [aws](#provider\_aws) | n/a |
| <a name="provider_random"></a> [random](#provider\_random) | n/a |

## Resources

| Name | Type |
|------|------|
| [aws_iam_policy_document.lambda](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_partition.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/partition) | data source |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_cc_list"></a> [cc\_list](#input\_cc\_list) | Comma-separated list of email addresses to CC on this case.  At least one email address is required. | `string` | n/a | yes |
| <a name="input_communication_body"></a> [communication\_body](#input\_communication\_body) | Text for body of the communication sent to support.  The variable 'account\_id' can be used within the text if preceded by a dollar sign and optionally enclosed by curly braces. | `string` | n/a | yes |
| <a name="input_subject"></a> [subject](#input\_subject) | Text for 'Subject' field of the communication sent to support.  The variable 'account\_id' can be used within the text if preceded by a dollar sign and optionally enclosed by curly braces. | `string` | n/a | yes |
| <a name="input_log_level"></a> [log\_level](#input\_log\_level) | Log level of the lambda output, one of: debug, info, warning, error, critical | `string` | `"info"` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_aws_cloudwatch_event_rule"></a> [aws\_cloudwatch\_event\_rule](#output\_aws\_cloudwatch\_event\_rule) | The cloudwatch event rule object |
| <a name="output_aws_cloudwatch_event_target"></a> [aws\_cloudwatch\_event\_target](#output\_aws\_cloudwatch\_event\_target) | The cloudWatch event target object |
| <a name="output_aws_lambda_permission_events"></a> [aws\_lambda\_permission\_events](#output\_aws\_lambda\_permission\_events) | The lambda permission object for cloudwatch event triggers |
| <a name="output_lambda"></a> [lambda](#output\_lambda) | The lambda module object |

<!-- END TFDOCS -->
