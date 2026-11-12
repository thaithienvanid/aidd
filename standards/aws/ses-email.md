---
id: aws/ses-email
type: opinionated
fills: [product-defaults:email-provider]
default: true
implements: product-defaults:transactional_email
roles: [architect, developer, sre, reviewer]
when_changed: ["**/mail/**", "**/email/**", "**/emails/**", "**/ses*.tf"]
why: "Amazon SES sends the product's email from the AWS account the project already runs, through an AWS SDK, its SMTP interface, or its API. Easy DKIM and bounce and complaint notifications come built in."
maturity: established
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
citation:
  url: https://docs.aws.amazon.com/ses/latest/dg/Welcome.html
  quote: "an easy, cost-effective way for you to send and receive email"
alternatives: [Postmark, SendGrid, Mailgun, Resend]
status: active
---

# Amazon SES sends the transactional email on AWS

It answers the email-provider choice of `aidd-team:product-defaults` on AWS. SES is an AWS service, with no software license of its own to mind.

## What the team does

- Verify the sending domain with Easy DKIM, and publish its SPF and DMARC records from the infrastructure code.
- Send transactional mail from a subdomain of its own, apart from any marketing mail, so one stream's reputation never harms the other.
- Call SES through an AWS SDK from one mail module, never from scattered call sites.
- Publish bounces and complaints to Amazon SNS. Stop mailing an address after a hard bounce or a complaint.
- Grant the sending role permission to send from the verified identity only.
