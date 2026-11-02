# /// script
# requires-python = ">=3.11"
# dependencies = ["fpdf2==2.8.5"]
# ///
"""Build the EC2 price sheet the demo knowledge base is seeded with.

Usage:
    uv run scripts/build_demo_pricing_pdf.py

Writes ``infrastructure/demo_assets/ec2-on-demand-pricing.pdf``, which
:mod:`infrastructure.demo_data` registers as the source of the demo
``AWS EC2 Pricing`` knowledge base. ``fpdf2`` comes from the inline script
metadata above, so it is never a dependency of the backend itself. Edit
:data:`_PRICES` and re-run it when the figures need refreshing, then commit
the regenerated PDF.
"""

from pathlib import Path

from fpdf import FPDF

#: Where the PDF is written, relative to this file.
_OUTPUT = (
    Path(__file__).resolve().parent.parent
    / "infrastructure"
    / "demo_assets"
    / "ec2-on-demand-pricing.pdf"
)

#: When the figures were taken from the AWS price list.
_AS_OF = "November 2026"

#: Hours in the billing month the monthly figures assume (AWS's own convention).
_HOURS_PER_MONTH = 730

#: Regions the sheet covers -- the ones the walkthrough's prompt offers.
_REGIONS = ("us-east-1", "us-east-2", "us-west-2")

#: ``(instance type, vCPU, memory GiB, processor, USD per hour)``: Linux,
#: shared tenancy, On-Demand. The price is the same in all of :data:`_REGIONS`.
_PRICES = (
    ("t4g.nano", 2, 0.5, "AWS Graviton2 (Arm)", 0.0042),
    ("t4g.micro", 2, 1, "AWS Graviton2 (Arm)", 0.0084),
    ("t4g.small", 2, 2, "AWS Graviton2 (Arm)", 0.0168),
    ("t4g.medium", 2, 4, "AWS Graviton2 (Arm)", 0.0336),
    ("t4g.large", 2, 8, "AWS Graviton2 (Arm)", 0.0672),
    ("t3.micro", 2, 1, "Intel Xeon (x86_64)", 0.0104),
    ("t3a.micro", 2, 1, "AMD EPYC (x86_64)", 0.0094),
    ("t2.micro", 1, 1, "Intel Xeon (x86_64)", 0.0116),
    ("c6g.medium", 1, 2, "AWS Graviton2 (Arm)", 0.034),
    ("m6g.medium", 1, 4, "AWS Graviton2 (Arm)", 0.0385),
)

#: Notes printed under the tables.
_NOTES = (
    "Prices are for Linux, shared tenancy, On-Demand, and exclude tax.",
    f"Monthly cost = hourly price x {_HOURS_PER_MONTH} hours.",
    "Storage is billed separately: an EBS gp3 volume costs USD 0.08 per GB-month, "
    "so the default 8 GB root volume adds USD 0.64 per month.",
    "A public IPv4 address costs USD 0.005 per hour (USD 3.65 per month).",
    "Burstable types (t2, t3, t3a, t4g) can incur extra charges for CPU credits "
    "when they run above their baseline in unlimited mode.",
    "Reference figures prepared for the A2Flow demo. Check the AWS pricing page "
    "before relying on them.",
)


def main() -> None:
    """Render the price sheet and write it to :data:`_OUTPUT`."""
    pdf = FPDF()
    pdf.set_title("Amazon EC2 On-Demand Pricing")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "Amazon EC2 On-Demand Pricing", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(
        0,
        7,
        f"Linux instances in {', '.join(_REGIONS)} - as of {_AS_OF}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 9, "Instance types", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    with pdf.table(col_widths=(30, 14, 26, 50, 30, 32)) as table:
        table.row(
            (
                "Instance type",
                "vCPU",
                "RAM (GiB)",
                "Processor",
                "USD per hour",
                "USD per month",
            )
        )
        for name, vcpu, memory, processor, hourly in _PRICES:
            table.row(
                (
                    name,
                    str(vcpu),
                    f"{memory:g}",
                    processor,
                    f"{hourly:.4f}",
                    f"{hourly * _HOURS_PER_MONTH:.2f}",
                )
            )
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 9, "Prices by region", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(
        0,
        6,
        "These instance types cost the same in every region this sheet covers. "
        "Monthly cost in USD:",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(2)
    with pdf.table(col_widths=(40, *(50,) * len(_REGIONS))) as table:
        table.row(("Instance type", *_REGIONS))
        for name, _vcpu, _memory, _processor, hourly in _PRICES:
            monthly = f"{hourly * _HOURS_PER_MONTH:.2f}"
            table.row((name, *(monthly,) * len(_REGIONS)))
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 9, "Notes", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for note in _NOTES:
        pdf.multi_cell(0, 6, f"- {note}", new_x="LMARGIN", new_y="NEXT")

    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(_OUTPUT))


if __name__ == "__main__":
    main()
