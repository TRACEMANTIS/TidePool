"""Pretext template library for phishing simulations.

Provides a curated collection of built-in pretext email templates across
multiple categories (IT/Security, HR, Finance, Executive, Vendor), each
with difficulty ratings, variable support, and red-flag annotations for
training purposes.
"""

from __future__ import annotations

from typing import Any

from app.pretext.variables import resolve_variables, list_variables_in_template


# ---------------------------------------------------------------------------
# HTML helpers -- shared styling fragments
# ---------------------------------------------------------------------------

def _wrap_email_html(body_content: str, footer: str = "") -> str:
    """Wrap body content in a standard email HTML shell with inline styles."""
    return (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>\n'
        '<body style="margin:0;padding:0;background-color:#f4f4f4;font-family:Arial,Helvetica,sans-serif;">\n'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f4;">\n'
        '<tr><td align="center" style="padding:20px 0;">\n'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        'style="background-color:#ffffff;border:1px solid #dddddd;border-radius:4px;">\n'
        f'{body_content}\n'
        '</table>\n'
        f'{footer}\n'
        '</td></tr>\n'
        '</table>\n'
        '</body>\n'
        '</html>'
    )


def _header_bar(bg_color: str, title: str) -> str:
    """Generate a colored header bar row for the email table."""
    return (
        f'<tr><td style="background-color:{bg_color};padding:20px 30px;'
        f'border-radius:4px 4px 0 0;">'
        f'<h1 style="margin:0;color:#ffffff;font-size:20px;font-weight:bold;">{title}</h1>'
        '</td></tr>'
    )


def _body_cell(content: str) -> str:
    """Wrap content in a padded table cell."""
    return (
        f'<tr><td style="padding:25px 30px;color:#333333;font-size:14px;line-height:1.6;">'
        f'{content}'
        '</td></tr>'
    )


def _button(url_var: str, label: str, color: str = "#0066cc") -> str:
    """Generate a CTA button using the given variable for the URL."""
    return (
        f'<p style="text-align:center;margin:25px 0;">'
        f'<a href="{{{{{url_var}}}}}" style="display:inline-block;padding:12px 30px;'
        f'background-color:{color};color:#ffffff;text-decoration:none;'
        f'border-radius:4px;font-weight:bold;font-size:14px;">{label}</a></p>'
    )


def _footer_text() -> str:
    """Standard email footer."""
    return (
        '<p style="margin:20px 0 0;padding-top:15px;border-top:1px solid #eeeeee;'
        'font-size:11px;color:#999999;">'
        'This message was sent by {{company}} IT Services.<br>'
        'If you did not expect this email, contact {{support_email}}.</p>'
    )


def _external_footer() -> str:
    """Footer block outside the main email table."""
    return (
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0">'
        '<tr><td style="padding:10px 30px;font-size:11px;color:#999999;text-align:center;">'
        'You are receiving this because you are an employee of {{company}}.<br>'
        'To unsubscribe from notifications, update your preferences in the portal.'
        '</td></tr></table>'
    )


# ---------------------------------------------------------------------------
# Built-in pretext templates
# ---------------------------------------------------------------------------

_PRETEXTS: dict[str, dict[str, Any]] = {}


def _register(pretext: dict[str, Any]) -> None:
    """Register a pretext template in the library."""
    _PRETEXTS[pretext["id"]] = pretext


# ===== IT / Security (difficulty 1-3) ======================================

_register({
    "id": "it_password_reset",
    "name": "Password Expiration Warning",
    "category": "IT",
    "difficulty": 2,
    "description": "Warns the user their password expires in 24 hours and directs them to a reset portal.",
    "subject": "Action Required: Your Password Expires in 24 Hours",
    "body_html": _wrap_email_html(
        _header_bar("#cc3300", "{{company}} -- Password Expiration Notice")
        + _body_cell(
            '<p>Dear {{first_name}},</p>'
            '<p>Our records indicate that your network password for '
            '<strong>{{email}}</strong> will expire in <strong>24 hours</strong>.</p>'
            '<p>To avoid losing access to your email, VPN, and internal systems, '
            'please reset your password immediately using the link below.</p>'
            + _button("login_url", "Reset Password Now", "#cc3300")
            + '<p>If you have already updated your password recently, you can '
            'safely disregard this message.</p>'
            '<p>Thank you,<br>{{company}} IT Support<br>{{support_email}}</p>'
            + _footer_text()
        ),
        _external_footer(),
    ),
    "body_text": (
        "Dear {{first_name}},\n\n"
        "Our records indicate that your network password for {{email}} "
        "will expire in 24 hours.\n\n"
        "To avoid losing access to your email, VPN, and internal systems, "
        "please reset your password immediately:\n\n"
        "{{login_url}}\n\n"
        "If you have already updated your password recently, you can "
        "safely disregard this message.\n\n"
        "Thank you,\n"
        "{{company}} IT Support\n"
        "{{support_email}}"
    ),
    "variables_used": ["first_name", "email", "company", "login_url", "support_email"],
    "red_flags": [
        "Creates artificial urgency with 24-hour deadline",
        "Links to an external password reset page instead of internal SSO",
        "Sender address may not match the organization's actual IT domain",
        "Does not address the user by employee ID or include a ticket number",
    ],
})

_register({
    "id": "it_mfa_enrollment",
    "name": "Mandatory MFA Enrollment",
    "category": "IT",
    "difficulty": 2,
    "description": "Notifies the user of a mandatory MFA enrollment deadline with a setup link.",
    "subject": "Action Required: Multi-Factor Authentication Enrollment",
    "body_html": _wrap_email_html(
        _header_bar("#0066cc", "{{company}} -- Security Update")
        + _body_cell(
            '<p>Hello {{first_name}},</p>'
            '<p>As part of our ongoing commitment to security, {{company}} is '
            'requiring all employees to enroll in Multi-Factor Authentication (MFA) '
            'by <strong>{{date}}</strong>.</p>'
            '<p>This change affects your account: <strong>{{email}}</strong></p>'
            '<p>Enrollment takes less than 5 minutes. You will need your '
            'mobile device to complete the process.</p>'
            + _button("login_url", "Enroll in MFA", "#0066cc")
            + '<p>If you have questions, contact the helpdesk at {{support_email}}.</p>'
            '<p>Best regards,<br>{{from_name}}<br>{{company}} Information Security</p>'
            + _footer_text()
        ),
        _external_footer(),
    ),
    "body_text": (
        "Hello {{first_name}},\n\n"
        "As part of our ongoing commitment to security, {{company}} is "
        "requiring all employees to enroll in Multi-Factor Authentication "
        "(MFA) by {{date}}.\n\n"
        "This change affects your account: {{email}}\n\n"
        "Enrollment takes less than 5 minutes. You will need your mobile "
        "device to complete the process.\n\n"
        "Enroll here: {{login_url}}\n\n"
        "If you have questions, contact the helpdesk at {{support_email}}.\n\n"
        "Best regards,\n"
        "{{from_name}}\n"
        "{{company}} Information Security"
    ),
    "variables_used": ["first_name", "email", "company", "date", "login_url", "support_email", "from_name"],
    "red_flags": [
        "Enrollment link points to a non-corporate domain",
        "Requests mobile device interaction from an email prompt",
        "Generic deadline without referencing an internal policy number",
    ],
})

_register({
    "id": "it_system_update",
    "name": "Scheduled System Maintenance",
    "category": "IT",
    "difficulty": 1,
    "description": "Announces system maintenance and asks users to verify login credentials beforehand.",
    "subject": "Scheduled System Maintenance -- Please Verify Your Account",
    "body_html": _wrap_email_html(
        _header_bar("#336699", "System Maintenance Notification")
        + _body_cell(
            '<p>Dear {{first_name}},</p>'
            '<p>{{company}} IT will be performing scheduled maintenance on our '
            'core systems on <strong>{{date}}</strong> from 11:00 PM to 3:00 AM EST.</p>'
            '<p>To ensure uninterrupted access after the maintenance window, '
            'please verify your account credentials by logging in to the portal below.</p>'
            + _button("login_url", "Verify Account", "#336699")
            + '<p>During the maintenance window, the following services may be '
            'temporarily unavailable:</p>'
            '<ul style="margin:10px 0;">'
            '<li>Email (Outlook/OWA)</li>'
            '<li>VPN Remote Access</li>'
            '<li>SharePoint / OneDrive</li>'
            '</ul>'
            '<p>We apologize for any inconvenience.</p>'
            '<p>Regards,<br>{{company}} IT Operations<br>{{support_email}}</p>'
            + _footer_text()
        ),
        _external_footer(),
    ),
    "body_text": (
        "Dear {{first_name}},\n\n"
        "{{company}} IT will be performing scheduled maintenance on our "
        "core systems on {{date}} from 11:00 PM to 3:00 AM EST.\n\n"
        "To ensure uninterrupted access after the maintenance window, "
        "please verify your account credentials:\n\n"
        "{{login_url}}\n\n"
        "During the maintenance window, the following services may be "
        "temporarily unavailable:\n"
        "- Email (Outlook/OWA)\n"
        "- VPN Remote Access\n"
        "- SharePoint / OneDrive\n\n"
        "We apologize for any inconvenience.\n\n"
        "Regards,\n"
        "{{company}} IT Operations\n"
        "{{support_email}}"
    ),
    "variables_used": ["first_name", "company", "date", "login_url", "support_email"],
    "red_flags": [
        "Asks users to 'verify credentials' -- legitimate maintenance does not require this",
        "External link for account verification",
        "No internal ticket or change-request number referenced",
        "Generic maintenance window without specific system names",
    ],
})

# ===== HR (difficulty 2-4) =================================================

_register({
    "id": "hr_benefits_enrollment",
    "name": "Open Enrollment Deadline",
    "category": "HR",
    "difficulty": 3,
    "description": "Reminds employees about benefits open enrollment with a portal link.",
    "subject": "Open Enrollment Closes {{date}} -- Review Your Benefits",
    "body_html": _wrap_email_html(
        _header_bar("#2e7d32", "{{company}} Benefits -- Open Enrollment")
        + _body_cell(
            '<p>Dear {{first_name}} {{last_name}},</p>'
            '<p>This is a reminder that the annual benefits open enrollment period '
            'closes on <strong>{{date}}</strong>. If you do not make your selections '
            'by the deadline, your current elections will roll over unchanged.</p>'
            '<p>Please review and confirm your benefits selections for the upcoming '
            'plan year, including:</p>'
            '<ul style="margin:10px 0;">'
            '<li>Medical, dental, and vision coverage</li>'
            '<li>Life insurance and disability</li>'
            '<li>Flexible Spending Account (FSA) elections</li>'
            '<li>401(k) contribution changes</li>'
            '</ul>'
            + _button("login_url", "Review My Benefits", "#2e7d32")
            + '<p>If you have questions about your options, contact HR Benefits '
            'at {{support_email}} or visit the Benefits FAQ on the intranet.</p>'
            '<p>Best regards,<br>{{from_name}}<br>{{company}} Human Resources</p>'
            + _footer_text()
        ),
        _external_footer(),
    ),
    "body_text": (
        "Dear {{first_name}} {{last_name}},\n\n"
        "This is a reminder that the annual benefits open enrollment period "
        "closes on {{date}}. If you do not make your selections by the "
        "deadline, your current elections will roll over unchanged.\n\n"
        "Please review and confirm your benefits selections for the "
        "upcoming plan year, including:\n"
        "- Medical, dental, and vision coverage\n"
        "- Life insurance and disability\n"
        "- Flexible Spending Account (FSA) elections\n"
        "- 401(k) contribution changes\n\n"
        "Review your benefits: {{login_url}}\n\n"
        "If you have questions, contact HR Benefits at {{support_email}}.\n\n"
        "Best regards,\n"
        "{{from_name}}\n"
        "{{company}} Human Resources"
    ),
    "variables_used": ["first_name", "last_name", "company", "date", "login_url", "support_email", "from_name"],
    "red_flags": [
        "Benefits portal link may not match the company's actual HRIS domain",
        "Deadline creates urgency to act quickly without verifying",
        "No employee ID or enrollment confirmation number included",
    ],
})

_register({
    "id": "hr_policy_update",
    "name": "Employee Handbook Acknowledgment",
    "category": "HR",
    "difficulty": 2,
    "description": "Requests employees acknowledge an updated employee handbook.",
    "subject": "Updated Employee Handbook -- Acknowledgment Required by {{date}}",
    "body_html": _wrap_email_html(
        _header_bar("#1565c0", "{{company}} HR Policy Update")
        + _body_cell(
            '<p>Dear {{first_name}},</p>'
            '<p>We have made important updates to the {{company}} Employee '
            'Handbook. All employees are required to review the changes and '
            'submit their acknowledgment by <strong>{{date}}</strong>.</p>'
            '<p>Key updates include changes to:</p>'
            '<ul style="margin:10px 0;">'
            '<li>Remote work policy</li>'
            '<li>Paid time off accrual</li>'
            '<li>Acceptable use of company technology</li>'
            '<li>Anti-harassment and workplace conduct</li>'
            '</ul>'
            '<p>Please review the updated handbook and sign the acknowledgment form:</p>'
            + _button("login_url", "Review and Acknowledge", "#1565c0")
            + '<p>Failure to acknowledge by the deadline may affect your '
            'standing with the company.</p>'
            '<p>Thank you,<br>{{company}} Human Resources<br>{{support_email}}</p>'
            + _footer_text()
        ),
        _external_footer(),
    ),
    "body_text": (
        "Dear {{first_name}},\n\n"
        "We have made important updates to the {{company}} Employee "
        "Handbook. All employees are required to review the changes and "
        "submit their acknowledgment by {{date}}.\n\n"
        "Key updates include changes to:\n"
        "- Remote work policy\n"
        "- Paid time off accrual\n"
        "- Acceptable use of company technology\n"
        "- Anti-harassment and workplace conduct\n\n"
        "Review and acknowledge: {{login_url}}\n\n"
        "Failure to acknowledge by the deadline may affect your standing "
        "with the company.\n\n"
        "Thank you,\n"
        "{{company}} Human Resources\n"
        "{{support_email}}"
    ),
    "variables_used": ["first_name", "company", "date", "login_url", "support_email"],
    "red_flags": [
        "Implicit threat about 'standing with the company' to pressure action",
        "Acknowledgment link points outside the HRIS system",
        "No reference to a specific policy version or revision number",
        "Generic list of updates that could apply to any company",
    ],
})

_register({
    "id": "hr_org_announcement",
    "name": "Organizational Restructure Notice",
    "category": "HR",
    "difficulty": 4,
    "description": "Announces organizational changes and directs users to a details page.",
    "subject": "Organizational Changes Effective {{date}} -- Please Review",
    "body_html": _wrap_email_html(
        _header_bar("#4527a0", "Confidential: Organizational Update")
        + _body_cell(
            '<p>Dear {{first_name}},</p>'
            '<p>I am writing to share some important organizational changes that '
            'will take effect on <strong>{{date}}</strong>. As part of our ongoing '
            'efforts to align our teams with strategic priorities, the following '
            'restructuring has been approved by the executive leadership team.</p>'
            '<p>These changes will directly impact the <strong>{{department}}</strong> '
            'team. A detailed summary of the new reporting structure, role changes, '
            'and team realignments is available in the document linked below.</p>'
            + _button("login_url", "View Restructure Details", "#4527a0")
            + '<p>I understand this may raise questions. We will be holding a '
            'town hall on {{date}} at 2:00 PM to discuss these changes. Calendar '
            'invites will follow shortly.</p>'
            '<p>Please treat this information as confidential until the official '
            'announcement.</p>'
            '<p>Sincerely,<br>{{from_name}}<br>SVP, Human Resources<br>{{company}}</p>'
        ),
        _external_footer(),
    ),
    "body_text": (
        "Dear {{first_name}},\n\n"
        "I am writing to share some important organizational changes that "
        "will take effect on {{date}}. As part of our ongoing efforts to "
        "align our teams with strategic priorities, the following "
        "restructuring has been approved by the executive leadership team.\n\n"
        "These changes will directly impact the {{department}} team. A "
        "detailed summary is available here:\n\n"
        "{{login_url}}\n\n"
        "I understand this may raise questions. We will be holding a town "
        "hall on {{date}} at 2:00 PM to discuss these changes.\n\n"
        "Please treat this information as confidential until the official "
        "announcement.\n\n"
        "Sincerely,\n"
        "{{from_name}}\n"
        "SVP, Human Resources\n"
        "{{company}}"
    ),
    "variables_used": ["first_name", "department", "company", "date", "login_url", "from_name"],
    "red_flags": [
        "Marked 'Confidential' to discourage the recipient from verifying",
        "Document link goes to an external site rather than the company intranet",
        "Uses department personalization to make it seem specifically targeted",
    ],
})

# ===== Finance (difficulty 2-4) ============================================

_register({
    "id": "fin_invoice_approval",
    "name": "Invoice Pending Approval",
    "category": "FINANCE",
    "difficulty": 3,
    "description": "Notifies a user that an invoice requires their approval in the finance portal.",
    "subject": "Invoice #{{invoice_number}} Requires Your Approval",
    "body_html": _wrap_email_html(
        _header_bar("#e65100", "{{company}} Accounts Payable")
        + _body_cell(
            '<p>Dear {{first_name}},</p>'
            '<p>An invoice has been submitted that requires your approval before '
            'payment can be processed.</p>'
            '<table style="width:100%;border-collapse:collapse;margin:15px 0;" '
            'cellpadding="8" cellspacing="0">'
            '<tr style="background-color:#f5f5f5;">'
            '<td style="border:1px solid #ddd;font-weight:bold;">Invoice #</td>'
            '<td style="border:1px solid #ddd;">{{invoice_number}}</td></tr>'
            '<tr>'
            '<td style="border:1px solid #ddd;font-weight:bold;">Vendor</td>'
            '<td style="border:1px solid #ddd;">{{vendor_name}}</td></tr>'
            '<tr style="background-color:#f5f5f5;">'
            '<td style="border:1px solid #ddd;font-weight:bold;">Amount</td>'
            '<td style="border:1px solid #ddd;">{{invoice_amount}}</td></tr>'
            '<tr>'
            '<td style="border:1px solid #ddd;font-weight:bold;">Due Date</td>'
            '<td style="border:1px solid #ddd;">{{date}}</td></tr>'
            '</table>'
            '<p>Please review the invoice details and approve or reject it '
            'through the finance portal:</p>'
            + _button("login_url", "Review Invoice", "#e65100")
            + '<p>Invoices not approved within 48 hours will be escalated to '
            'your manager.</p>'
            '<p>Regards,<br>{{company}} Accounts Payable<br>{{support_email}}</p>'
            + _footer_text()
        ),
        _external_footer(),
    ),
    "body_text": (
        "Dear {{first_name}},\n\n"
        "An invoice has been submitted that requires your approval.\n\n"
        "Invoice #: {{invoice_number}}\n"
        "Vendor: {{vendor_name}}\n"
        "Amount: {{invoice_amount}}\n"
        "Due Date: {{date}}\n\n"
        "Please review and approve: {{login_url}}\n\n"
        "Invoices not approved within 48 hours will be escalated.\n\n"
        "Regards,\n"
        "{{company}} Accounts Payable\n"
        "{{support_email}}"
    ),
    "variables_used": [
        "first_name", "company", "date", "login_url", "support_email",
        "invoice_number", "vendor_name", "invoice_amount",
    ],
    "red_flags": [
        "Escalation threat creates urgency to approve without verifying",
        "Finance portal link may differ from the company's actual ERP URL",
        "Invoice details may not match any real purchase order",
    ],
})

_register({
    "id": "fin_expense_report",
    "name": "Expense Report Rejected",
    "category": "FINANCE",
    "difficulty": 2,
    "description": "Informs the user their expense report was rejected and needs resubmission.",
    "subject": "Expense Report Rejected -- Action Required",
    "body_html": _wrap_email_html(
        _header_bar("#bf360c", "{{company}} Expense Management")
        + _body_cell(
            '<p>Dear {{first_name}},</p>'
            '<p>Your recent expense report has been <strong style="color:#cc0000;">'
            'rejected</strong> by your approver due to missing or incomplete '
            'documentation.</p>'
            '<p>To resolve this, please:</p>'
            '<ol style="margin:10px 0;">'
            '<li>Log in to the expense management portal</li>'
            '<li>Review the rejection comments on your report</li>'
            '<li>Attach the required receipts or documentation</li>'
            '<li>Resubmit the report for approval</li>'
            '</ol>'
            + _button("login_url", "View Expense Report", "#bf360c")
            + '<p>Please note that unreimbursed expense reports older than 60 days '
            'will be automatically closed.</p>'
            '<p>Questions? Contact {{support_email}}.</p>'
            '<p>Thank you,<br>{{company}} Finance Team</p>'
            + _footer_text()
        ),
        _external_footer(),
    ),
    "body_text": (
        "Dear {{first_name}},\n\n"
        "Your recent expense report has been REJECTED by your approver "
        "due to missing or incomplete documentation.\n\n"
        "To resolve this, please:\n"
        "1. Log in to the expense management portal\n"
        "2. Review the rejection comments on your report\n"
        "3. Attach the required receipts or documentation\n"
        "4. Resubmit the report for approval\n\n"
        "View your expense report: {{login_url}}\n\n"
        "Unreimbursed expense reports older than 60 days will be "
        "automatically closed.\n\n"
        "Questions? Contact {{support_email}}.\n\n"
        "Thank you,\n"
        "{{company}} Finance Team"
    ),
    "variables_used": ["first_name", "company", "login_url", "support_email"],
    "red_flags": [
        "Does not reference a specific expense report ID or amount",
        "External portal link for financial data",
        "Urgency implied by the 60-day auto-close policy",
        "No approver name mentioned",
    ],
})

_register({
    "id": "fin_wire_confirmation",
    "name": "Wire Transfer Confirmation",
    "category": "FINANCE",
    "difficulty": 4,
    "description": "Requests confirmation of a pending wire transfer with financial details.",
    "subject": "Wire Transfer Confirmation Required -- Ref #{{wire_ref}}",
    "body_html": _wrap_email_html(
        _header_bar("#1a237e", "{{company}} Treasury Operations")
        + _body_cell(
            '<p>Dear {{first_name}},</p>'
            '<p>A wire transfer has been initiated from the {{department}} '
            'operating account and requires your confirmation before it can '
            'be released by the bank.</p>'
            '<table style="width:100%;border-collapse:collapse;margin:15px 0;" '
            'cellpadding="8" cellspacing="0">'
            '<tr style="background-color:#f5f5f5;">'
            '<td style="border:1px solid #ddd;font-weight:bold;">Reference</td>'
            '<td style="border:1px solid #ddd;">{{wire_ref}}</td></tr>'
            '<tr>'
            '<td style="border:1px solid #ddd;font-weight:bold;">Amount</td>'
            '<td style="border:1px solid #ddd;">{{wire_amount}}</td></tr>'
            '<tr style="background-color:#f5f5f5;">'
            '<td style="border:1px solid #ddd;font-weight:bold;">Beneficiary</td>'
            '<td style="border:1px solid #ddd;">{{beneficiary_name}}</td></tr>'
            '<tr>'
            '<td style="border:1px solid #ddd;font-weight:bold;">Date</td>'
            '<td style="border:1px solid #ddd;">{{date}}</td></tr>'
            '</table>'
            '<p>For security purposes, please confirm this transaction through '
            'the secure verification portal within <strong>4 hours</strong>:</p>'
            + _button("login_url", "Confirm Wire Transfer", "#1a237e")
            + '<p>If you did not authorize this transfer, please contact Treasury '
            'Operations immediately at {{support_email}}.</p>'
            '<p>Regards,<br>{{from_name}}<br>Treasury Operations<br>{{company}}</p>'
        ),
        _external_footer(),
    ),
    "body_text": (
        "Dear {{first_name}},\n\n"
        "A wire transfer has been initiated from the {{department}} "
        "operating account and requires your confirmation.\n\n"
        "Reference: {{wire_ref}}\n"
        "Amount: {{wire_amount}}\n"
        "Beneficiary: {{beneficiary_name}}\n"
        "Date: {{date}}\n\n"
        "Please confirm within 4 hours: {{login_url}}\n\n"
        "If you did not authorize this transfer, contact Treasury "
        "Operations immediately at {{support_email}}.\n\n"
        "Regards,\n"
        "{{from_name}}\n"
        "Treasury Operations\n"
        "{{company}}"
    ),
    "variables_used": [
        "first_name", "department", "company", "date", "login_url",
        "support_email", "from_name", "wire_ref", "wire_amount", "beneficiary_name",
    ],
    "red_flags": [
        "Extremely tight 4-hour confirmation window to pressure quick action",
        "Verification portal link is external, not the company's banking portal",
        "Wire transfer details should be verified through the banking system directly",
    ],
})

# ===== Executive (difficulty 3-5) ==========================================

_register({
    "id": "exec_board_materials",
    "name": "Board Meeting Materials",
    "category": "EXECUTIVE",
    "difficulty": 4,
    "description": "Shares confidential board meeting materials with a download link.",
    "subject": "Confidential: Board Meeting Materials for {{date}}",
    "body_html": _wrap_email_html(
        _header_bar("#263238", "{{company}} -- Board of Directors")
        + _body_cell(
            '<p>Dear {{first_name}},</p>'
            '<p>Attached please find the board meeting materials for the upcoming '
            'session on <strong>{{date}}</strong>. These documents are classified '
            'as <strong>Confidential</strong> and are intended solely for board '
            'members and designated senior leadership.</p>'
            '<p>The materials include:</p>'
            '<ul style="margin:10px 0;">'
            '<li>Quarterly financial summary and projections</li>'
            '<li>Strategic initiative progress report</li>'
            '<li>Compensation committee recommendations</li>'
            '<li>Risk and compliance update</li>'
            '</ul>'
            '<p>Due to the sensitive nature of these documents, they are hosted '
            'on our secure document portal rather than sent as attachments.</p>'
            + _button("login_url", "Access Board Materials", "#263238")
            + '<p>Please review the materials prior to the meeting. The portal '
            'link will expire 48 hours after the meeting concludes.</p>'
            '<p>Regards,<br>{{from_name}}<br>Corporate Secretary<br>{{company}}</p>'
        ),
    ),
    "body_text": (
        "Dear {{first_name}},\n\n"
        "Please find the board meeting materials for {{date}} on our "
        "secure document portal.\n\n"
        "The materials include:\n"
        "- Quarterly financial summary and projections\n"
        "- Strategic initiative progress report\n"
        "- Compensation committee recommendations\n"
        "- Risk and compliance update\n\n"
        "Access here: {{login_url}}\n\n"
        "The portal link will expire 48 hours after the meeting.\n\n"
        "Regards,\n"
        "{{from_name}}\n"
        "Corporate Secretary\n"
        "{{company}}"
    ),
    "variables_used": ["first_name", "company", "date", "login_url", "from_name"],
    "red_flags": [
        "Confidentiality label discourages the recipient from verifying with others",
        "Document portal link is external rather than a known board management platform",
        "No meeting ID, agenda number, or Diligent/BoardEffect reference",
    ],
})

_register({
    "id": "exec_strategy_review",
    "name": "Quarterly Strategy Review",
    "category": "EXECUTIVE",
    "difficulty": 5,
    "description": "Requests executive input on a quarterly strategy document via a shared link.",
    "subject": "Q4 Strategy Review -- Your Input Requested by {{date}}",
    "body_html": _wrap_email_html(
        _header_bar("#37474f", "Strategy & Planning")
        + _body_cell(
            '<p>{{first_name}},</p>'
            '<p>As we finalize the Q4 strategy review, I wanted to get your '
            'perspective on a few items before we present to the board next week. '
            'Given your role leading {{department}}, your input on the market '
            'positioning section would be especially valuable.</p>'
            '<p>I have shared the draft with you on the strategy portal. Could '
            'you review sections 3 and 4 and add your comments by '
            '<strong>{{date}}</strong>?</p>'
            + _button("login_url", "Open Strategy Document", "#37474f")
            + '<p>Let me know if you want to schedule 30 minutes to discuss '
            'before the deadline.</p>'
            '<p>Thanks,<br>{{from_name}}</p>'
        ),
    ),
    "body_text": (
        "{{first_name}},\n\n"
        "As we finalize the Q4 strategy review, I wanted to get your "
        "perspective on a few items before we present to the board next "
        "week. Given your role leading {{department}}, your input on the "
        "market positioning section would be especially valuable.\n\n"
        "I have shared the draft on the strategy portal. Could you review "
        "sections 3 and 4 and add comments by {{date}}?\n\n"
        "{{login_url}}\n\n"
        "Let me know if you want to schedule 30 minutes to discuss.\n\n"
        "Thanks,\n"
        "{{from_name}}"
    ),
    "variables_used": ["first_name", "department", "company", "date", "login_url", "from_name"],
    "red_flags": [
        "Informal tone from a senior leader may lower the recipient's guard",
        "Strategy portal link is external rather than SharePoint/Google Drive/Confluence",
        "References specific sections to create a sense of legitimacy",
    ],
})

_register({
    "id": "exec_calendar_invite",
    "name": "Urgent Meeting Request from CEO",
    "category": "EXECUTIVE",
    "difficulty": 3,
    "description": "A calendar meeting request appearing to come from the CEO.",
    "subject": "Meeting Request: Urgent Discussion -- {{from_name}}",
    "body_html": _wrap_email_html(
        _header_bar("#880e4f", "Meeting Request")
        + _body_cell(
            '<p>Hi {{first_name}},</p>'
            '<p>I need to discuss something with you urgently. Can you '
            'please confirm your availability for a brief meeting today or '
            'tomorrow?</p>'
            '<p>I have put together a short briefing document for context. '
            'Please review it before we meet:</p>'
            + _button("login_url", "View Briefing Document", "#880e4f")
            + '<p>Please confirm by replying to this email or accepting the '
            'calendar invite that will follow.</p>'
            '<p>Thanks,<br>{{from_name}}<br>CEO, {{company}}</p>'
        ),
    ),
    "body_text": (
        "Hi {{first_name}},\n\n"
        "I need to discuss something with you urgently. Can you confirm "
        "your availability for a brief meeting today or tomorrow?\n\n"
        "Please review this briefing document before we meet:\n"
        "{{login_url}}\n\n"
        "Please confirm by replying to this email.\n\n"
        "Thanks,\n"
        "{{from_name}}\n"
        "CEO, {{company}}"
    ),
    "variables_used": ["first_name", "company", "login_url", "from_name"],
    "red_flags": [
        "CEO making a direct urgent request to an individual bypasses normal channels",
        "Vague subject matter ('something') creates curiosity without specifics",
        "Briefing document link is external",
        "Real CEO calendar invites come through the calendar system, not email links",
    ],
})

# ===== Vendor (difficulty 1-3) =============================================

_register({
    "id": "vendor_delivery",
    "name": "Package Delivery Notification",
    "category": "VENDOR",
    "difficulty": 1,
    "description": "Fake shipping notification with a tracking link.",
    "subject": "Your Package Is On Its Way -- Track Delivery",
    "body_html": _wrap_email_html(
        _header_bar("#795548", "Shipping Notification")
        + _body_cell(
            '<p>Dear {{first_name}} {{last_name}},</p>'
            '<p>Good news! A package addressed to you at <strong>{{company}}</strong> '
            'has been shipped and is on its way.</p>'
            '<table style="width:100%;border-collapse:collapse;margin:15px 0;" '
            'cellpadding="8" cellspacing="0">'
            '<tr style="background-color:#f5f5f5;">'
            '<td style="border:1px solid #ddd;font-weight:bold;">Tracking #</td>'
            '<td style="border:1px solid #ddd;">{{tracking_number}}</td></tr>'
            '<tr>'
            '<td style="border:1px solid #ddd;font-weight:bold;">Estimated Delivery</td>'
            '<td style="border:1px solid #ddd;">{{date}}</td></tr>'
            '<tr style="background-color:#f5f5f5;">'
            '<td style="border:1px solid #ddd;font-weight:bold;">Carrier</td>'
            '<td style="border:1px solid #ddd;">Express Logistics</td></tr>'
            '</table>'
            '<p>Track your package in real time:</p>'
            + _button("login_url", "Track My Package", "#795548")
            + '<p>If you were not expecting a delivery, please disregard this email.</p>'
            '<p>Thank you,<br>Express Logistics Shipping Team</p>'
        ),
        _external_footer(),
    ),
    "body_text": (
        "Dear {{first_name}} {{last_name}},\n\n"
        "A package addressed to you at {{company}} has been shipped.\n\n"
        "Tracking #: {{tracking_number}}\n"
        "Estimated Delivery: {{date}}\n"
        "Carrier: Express Logistics\n\n"
        "Track your package: {{login_url}}\n\n"
        "If you were not expecting a delivery, please disregard this email.\n\n"
        "Thank you,\n"
        "Express Logistics Shipping Team"
    ),
    "variables_used": ["first_name", "last_name", "company", "date", "login_url", "tracking_number"],
    "red_flags": [
        "Generic carrier name 'Express Logistics' -- not a recognized shipper",
        "Tracking link does not go to UPS/FedEx/USPS",
        "Recipient did not order anything",
        "No sender/return address information",
    ],
})

_register({
    "id": "vendor_contract",
    "name": "Contract Renewal Notice",
    "category": "VENDOR",
    "difficulty": 3,
    "description": "Notifies about an expiring vendor contract requiring renewal action.",
    "subject": "Contract Renewal: Agreement Expiring {{date}}",
    "body_html": _wrap_email_html(
        _header_bar("#00695c", "Contract Management")
        + _body_cell(
            '<p>Dear {{first_name}},</p>'
            '<p>This is a courtesy notification that the service agreement between '
            '<strong>{{company}}</strong> and our organization is scheduled to '
            'expire on <strong>{{date}}</strong>.</p>'
            '<p>To ensure uninterrupted service, we recommend reviewing the '
            'renewal terms at your earliest convenience. The updated agreement '
            'is available for your review on our contract portal.</p>'
            + _button("login_url", "Review Renewal Terms", "#00695c")
            + '<p>If your organization has decided not to renew, no action is '
            'required and the agreement will lapse on the expiration date.</p>'
            '<p>Please direct any questions to your account manager or '
            'contact us at {{support_email}}.</p>'
            '<p>Best regards,<br>{{from_name}}<br>Account Management</p>'
            + _footer_text()
        ),
        _external_footer(),
    ),
    "body_text": (
        "Dear {{first_name}},\n\n"
        "This is a courtesy notification that the service agreement between "
        "{{company}} and our organization is scheduled to expire on {{date}}.\n\n"
        "To ensure uninterrupted service, please review the renewal terms:\n\n"
        "{{login_url}}\n\n"
        "If your organization has decided not to renew, no action is required.\n\n"
        "Please direct questions to {{support_email}}.\n\n"
        "Best regards,\n"
        "{{from_name}}\n"
        "Account Management"
    ),
    "variables_used": ["first_name", "company", "date", "login_url", "support_email", "from_name"],
    "red_flags": [
        "Vendor name is vague -- no specific company identified",
        "Contract portal link is external and unfamiliar",
        "Service interruption implication creates urgency",
    ],
})

_register({
    "id": "vendor_service_alert",
    "name": "Service Disruption Alert",
    "category": "VENDOR",
    "difficulty": 2,
    "description": "Alerts about a vendor service disruption requiring credential verification.",
    "subject": "Service Disruption Alert -- Immediate Action Required",
    "body_html": _wrap_email_html(
        _header_bar("#d32f2f", "Service Alert")
        + _body_cell(
            '<p>Dear {{company}} Administrator,</p>'
            '<p>We are experiencing a service disruption that may affect your '
            'organization\'s access to our platform. Our engineering team is '
            'working to resolve the issue.</p>'
            '<p>In the meantime, some user sessions may have been interrupted. '
            'To restore access, we ask that affected users re-authenticate '
            'through our service recovery portal.</p>'
            + _button("login_url", "Restore Access", "#d32f2f")
            + '<p><strong>Current Status:</strong></p>'
            '<ul style="margin:10px 0;">'
            '<li>Issue identified: {{date}} at 09:15 AM UTC</li>'
            '<li>Services affected: Authentication, API access</li>'
            '<li>Estimated resolution: 2-4 hours</li>'
            '</ul>'
            '<p>We apologize for the inconvenience and will provide updates '
            'on our status page.</p>'
            '<p>Regards,<br>{{from_name}}<br>Service Operations Center</p>'
        ),
        _external_footer(),
    ),
    "body_text": (
        "Dear {{company}} Administrator,\n\n"
        "We are experiencing a service disruption that may affect your "
        "organization's access to our platform.\n\n"
        "To restore access, please re-authenticate:\n"
        "{{login_url}}\n\n"
        "Current Status:\n"
        "- Issue identified: {{date}} at 09:15 AM UTC\n"
        "- Services affected: Authentication, API access\n"
        "- Estimated resolution: 2-4 hours\n\n"
        "We apologize for the inconvenience.\n\n"
        "Regards,\n"
        "{{from_name}}\n"
        "Service Operations Center"
    ),
    "variables_used": ["company", "date", "login_url", "from_name"],
    "red_flags": [
        "Asks users to re-authenticate through a 'recovery portal' -- legitimate vendors do not do this",
        "Generic vendor identity -- no specific service or company named",
        "Urgency created by active 'disruption' language",
        "No incident ticket number or status page URL from a known provider",
    ],
})


# ---------------------------------------------------------------------------
# PretextLibrary class
# ---------------------------------------------------------------------------

class PretextLibrary:
    """Interface for browsing, retrieving, and rendering pretext templates.

    All built-in templates are registered at module load time.  This class
    provides filtered listing, single-template retrieval, and variable
    rendering.
    """

    def list_pretexts(
        self,
        category: str | None = None,
        difficulty: int | None = None,
    ) -> list[dict[str, Any]]:
        """List pretext templates with optional filtering.

        Parameters
        ----------
        category:
            Filter by category (e.g. ``"IT"``, ``"HR"``, ``"FINANCE"``,
            ``"EXECUTIVE"``, ``"VENDOR"``).  Case-insensitive.
        difficulty:
            Filter by exact difficulty level (1-5).

        Returns
        -------
        list[dict]
            List of pretext metadata dicts (without full body content).
        """
        results: list[dict[str, Any]] = []

        for pretext in _PRETEXTS.values():
            if category is not None:
                if pretext["category"].upper() != category.upper():
                    continue
            if difficulty is not None:
                if pretext["difficulty"] != difficulty:
                    continue

            results.append({
                "id": pretext["id"],
                "name": pretext["name"],
                "category": pretext["category"],
                "difficulty": pretext["difficulty"],
                "description": pretext["description"],
                "subject": pretext["subject"],
                "variables_used": pretext["variables_used"],
                "red_flags": pretext["red_flags"],
            })

        return results

    def get_pretext(self, pretext_id: str) -> dict[str, Any] | None:
        """Retrieve a full pretext template by ID.

        Parameters
        ----------
        pretext_id:
            The unique identifier of the pretext.

        Returns
        -------
        dict | None
            The complete pretext dict, or ``None`` if not found.
        """
        return _PRETEXTS.get(pretext_id)

    def render_pretext(
        self,
        pretext_id: str,
        variables: dict[str, Any],
    ) -> dict[str, str] | None:
        """Render a pretext template with the given variables.

        This is a convenience method that resolves ``{{variable}}``
        placeholders in the subject, HTML body, and plain-text body.

        Parameters
        ----------
        pretext_id:
            The unique identifier of the pretext template.
        variables:
            Dict of variable values to substitute.  Should include both
            contact-level and campaign-level variables.

        Returns
        -------
        dict | None
            Dict with ``subject``, ``body_html``, and ``body_text`` keys,
            or ``None`` if the pretext ID is not found.
        """
        pretext = _PRETEXTS.get(pretext_id)
        if pretext is None:
            return None

        # Split variables into contact vs. campaign buckets for resolve_variables
        contact_keys = {"first_name", "last_name", "email", "department", "title", "custom_fields"}
        contact = {k: v for k, v in variables.items() if k in contact_keys}
        campaign_config = {k: v for k, v in variables.items() if k not in contact_keys}

        subject = resolve_variables(pretext["subject"], contact, campaign_config)
        body_html = resolve_variables(pretext["body_html"], contact, campaign_config)
        body_text = resolve_variables(pretext["body_text"], contact, campaign_config)

        return {
            "subject": subject,
            "body_html": body_html,
            "body_text": body_text,
        }
