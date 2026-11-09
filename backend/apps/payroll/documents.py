"""Printed payslips, on the business's own letterhead from its bill design."""

from decimal import Decimal
from typing import Any

from django.template.loader import render_to_string

from apps.sales.documents import letterhead

from .contributions import LINE_NAMES
from .models import Payslip

LABELS: dict[str, dict[str, str]] = {
    "en": {
        "payslip": "Payslip",
        "month": "Month",
        "employee": "Employee",
        "code": "Code",
        "department": "Department",
        "job_title": "Job",
        "days": "Days paid",
        "of": "of",
        "unpaid": "Unpaid days",
        "earnings": "Earnings",
        "deductions": "Deductions",
        "basic": "Basic salary",
        "income_tax": "Income tax",
        "gross": "Total earnings",
        "total_deductions": "Total deductions",
        "net": "Net pay",
        "projected": "Estimated taxable salary this tax year",
        "year_tax": "Income tax on it for the year",
        "signature": "Authorised signature",
        "eobi": "EOBI",
        "social_security": "Social security",
        "contributions": "EOBI and social security",
        "base": "On",
        "your_share": "Your share",
        "employer_share": "Employer's share",
        "employer_note": "The employer's share is paid on top of your pay, not taken from it.",
    },
    "ur": {
        "payslip": "تنخواہ کی پرچی",
        "month": "مہینہ",
        "employee": "ملازم",
        "code": "کوڈ",
        "department": "شعبہ",
        "job_title": "عہدہ",
        "days": "ادا شدہ دن",
        "of": "میں سے",
        "unpaid": "بغیر تنخواہ دن",
        "earnings": "آمدنی",
        "deductions": "کٹوتیاں",
        "basic": "بنیادی تنخواہ",
        "income_tax": "انکم ٹیکس",
        "gross": "کل آمدنی",
        "total_deductions": "کل کٹوتیاں",
        "net": "خالص تنخواہ",
        "projected": "اس ٹیکس سال کی متوقع قابل ٹیکس تنخواہ",
        "year_tax": "اس پر سال بھر کا انکم ٹیکس",
        "signature": "مجاز دستخط",
        "eobi": "ای او بی آئی",
        "social_security": "سوشل سیکیورٹی",
        "contributions": "ای او بی آئی اور سوشل سیکیورٹی",
        "base": "کس رقم پر",
        "your_share": "آپ کا حصہ",
        "employer_share": "آجر کا حصہ",
        "employer_note": "آجر کا حصہ آپ کی تنخواہ کے علاوہ ادا ہوتا ہے، اس میں سے نہیں کٹتا",
    },
    "ar": {
        "payslip": "قسيمة الراتب",
        "month": "الشهر",
        "employee": "الموظف",
        "code": "الرمز",
        "department": "القسم",
        "job_title": "الوظيفة",
        "days": "الأيام المدفوعة",
        "of": "من",
        "unpaid": "أيام بلا أجر",
        "earnings": "المستحقات",
        "deductions": "الاستقطاعات",
        "basic": "الراتب الأساسي",
        "income_tax": "ضريبة الدخل",
        "gross": "إجمالي المستحقات",
        "total_deductions": "إجمالي الاستقطاعات",
        "net": "صافي الراتب",
        "projected": "الراتب الخاضع للضريبة المقدر لهذه السنة الضريبية",
        "year_tax": "ضريبة الدخل عليه للسنة",
        "signature": "توقيع معتمد",
        "eobi": "EOBI",
        "social_security": "الضمان الاجتماعي",
        "contributions": "EOBI والضمان الاجتماعي",
        "base": "على مبلغ",
        "your_share": "حصتك",
        "employer_share": "حصة صاحب العمل",
        "employer_note": "يدفع صاحب العمل حصته فوق راتبك، ولا تُقتطع منه.",
    },
}


def _money(value: Decimal | str) -> str:
    return f"{Decimal(value):,.2f}"


def _days(value: Decimal) -> str:
    return f"{value.normalize():f}"


def payslip_html(payslip: Payslip, language: str) -> str:
    context = letterhead(language)
    labels = LABELS[language]
    lines: list[dict[str, Any]] = payslip.lines
    # "Basic" comes from the salary maths and the EOBI and social security lines from payroll;
    # every other line is the business's own wording.
    fixed = {"Basic": labels["basic"]} | {
        name: labels[scheme] for scheme, name in LINE_NAMES.items()
    }
    named = [{**line, "name": fixed.get(line["name"], line["name"])} for line in lines]
    contributions = [
        {
            "name": labels[row["scheme"]],
            "base": _money(row["base"]),
            "employee": _money(row["employee"]),
            "employer": _money(row["employer"]),
        }
        for row in payslip.contributions
    ]
    return render_to_string(
        "payroll/payslip.html",
        {
            **context,
            "labels": {**context["labels"], **labels},
            "payslip": payslip,
            "run": payslip.run,
            "employee": payslip.employee,
            "earnings": [
                {"name": line["name"], "amount": _money(line["amount"])}
                for line in named
                if line["kind"] == "earning"
            ],
            "deductions": [
                {"name": line["name"], "amount": _money(line["amount"])}
                for line in named
                if line["kind"] == "deduction"
            ],
            "paid_days": _days(payslip.paid_days),
            "unpaid_days": _days(payslip.unpaid_days) if payslip.unpaid_days else None,
            "gross": _money(payslip.gross),
            "tax": _money(payslip.tax),
            "total_deductions": _money(payslip.deductions + payslip.tax),
            "net": _money(payslip.net),
            "projected": _money(payslip.projected_income) if payslip.year_tax else None,
            "year_tax": _money(payslip.year_tax),
            "contributions": contributions,
        },
    )
