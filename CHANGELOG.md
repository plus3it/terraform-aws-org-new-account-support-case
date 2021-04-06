## terraform-aws-org-new-account-iam-role Change Log

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/) and this project adheres to [Semantic Versioning](http://semver.org/).

### unreleased
    
**Commit Delta**: [Change from 0.0.0 release](https://github.com/plus3it/terraform-aws-org-new-account-iam-role/compare/0.0.0...unreleased)

**Released**: tbd

**Summary**:
        
*   Updated the Terraform configuration to add the policy document to
    provide the Lambda with permissions for 
    organizations:DescribeCreateAccountStatus.
*   Modified the unit tests to replace the monkeypatched function for
    get_account_id with a call to moto organizations service to set up an 
    obtain an organizations account ID.

### 0.0.0

**Commit Delta**: N/A

**Released**: 2021.03.30

**Summary**:

*   Initial release!
