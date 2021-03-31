variable "company_name" {
  description = "Name of company requesting Enterprise Support of a new account."
  type        = string
}
variable "cc_list" {
  description = "Comma-separated list of email addresses to CC on this case.  At least one email address is required."
  type        = string
}
variable "log_level" {
  default     = "info"
  description = "Log level of the lambda output, one of: debug, info, warning, error, critical"
  type        = string
}
