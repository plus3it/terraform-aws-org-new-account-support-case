variable "cc_list" {
  description = "Comma-separated list of email addresses to CC on this case.  At least one email address is required."
  type        = string
}

variable "communication_body" {
  description = "Text for body of the communication sent to support.  The variable 'account_id' can be used within the text if preceded by a dollar sign and optionally enclosed by curly braces."
  type        = string
}

variable "event_types" {
  description = "Event types that will trigger this lambda"
  type        = set(string)
  default = [
    "CreateAccountResult",
    "InviteAccountToOrganization",
  ]

  validation {
    condition     = alltrue([for event in var.event_types : contains(["CreateAccountResult", "InviteAccountToOrganization"], event)])
    error_message = "Supported event_types include only: CreateAccountResult, InviteAccountToOrganization"
  }
}

variable "lambda" {
  description = "Map of any additional arguments for the upstream lambda module. See <https://github.com/terraform-aws-modules/terraform-aws-lambda>"
  type = object({
    artifacts_dir            = optional(string, "builds")
    create_package           = optional(bool, true)
    ephemeral_storage_size   = optional(number)
    ignore_source_code_hash  = optional(bool, true)
    local_existing_package   = optional(string)
    recreate_missing_package = optional(bool, false)
    s3_bucket                = optional(string)
    s3_existing_package      = optional(map(string))
    s3_prefix                = optional(string)
    store_on_s3              = optional(bool, false)
  })
  default = {}
}

variable "log_level" {
  default     = "info"
  description = "Log level of the lambda output, one of: debug, info, warning, error, critical"
  type        = string
}

variable "subject" {
  description = "Text for 'Subject' field of the communication sent to support.  The variable 'account_id' can be used within the text if preceded by a dollar sign and optionally enclosed by curly braces."
  type        = string
}

variable "tags" {
  default     = {}
  description = "Tags that are passed to resources"
  type        = map(string)
}
