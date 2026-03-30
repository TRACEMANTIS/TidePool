#!/usr/bin/env python3
"""Generate realistic test address book files for TidePool benchmarking.

Produces CSV and XLSX files at configurable size tiers (10K-400K rows) with
deterministic seeding for reproducible benchmarks. Does not depend on the
faker library -- all realistic data lists are embedded directly.

Usage:
    python3 generate_test_addressbooks.py
    python3 generate_test_addressbooks.py --tiers 10k,50k --formats csv
    python3 generate_test_addressbooks.py --seed 123 --output-dir /tmp/bench
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import string
import sys
import time
from datetime import date, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Embedded realistic data
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael",
    "Linda", "David", "Elizabeth", "William", "Barbara", "Richard", "Susan",
    "Joseph", "Jessica", "Thomas", "Sarah", "Christopher", "Karen", "Charles",
    "Lisa", "Daniel", "Nancy", "Matthew", "Betty", "Anthony", "Margaret",
    "Mark", "Sandra", "Donald", "Ashley", "Steven", "Kimberly", "Paul",
    "Emily", "Andrew", "Donna", "Joshua", "Michelle", "Kenneth", "Carol",
    "Kevin", "Amanda", "Brian", "Dorothy", "George", "Melissa", "Timothy",
    "Deborah", "Ronald", "Stephanie", "Edward", "Rebecca", "Jason", "Sharon",
    "Jeffrey", "Laura", "Ryan", "Cynthia", "Jacob", "Kathleen", "Gary",
    "Amy", "Nicholas", "Angela", "Eric", "Shirley", "Jonathan", "Anna",
    "Stephen", "Brenda", "Larry", "Pamela", "Justin", "Emma", "Scott",
    "Nicole", "Brandon", "Helen", "Benjamin", "Samantha", "Samuel",
    "Katherine", "Raymond", "Christine", "Gregory", "Debra", "Frank",
    "Rachel", "Alexander", "Carolyn", "Patrick", "Janet", "Jack", "Catherine",
    "Dennis", "Maria", "Jerry", "Heather", "Tyler", "Diane", "Aaron",
    "Ruth", "Jose", "Julie", "Adam", "Olivia", "Nathan", "Joyce", "Henry",
    "Virginia", "Douglas", "Victoria", "Peter", "Kelly", "Zachary", "Lauren",
    "Kyle", "Christina", "Noah", "Joan", "Ethan", "Evelyn", "Jeremy",
    "Judith", "Walter", "Megan", "Christian", "Andrea", "Keith", "Cheryl",
    "Roger", "Hannah", "Terry", "Jacqueline", "Austin", "Martha", "Sean",
    "Gloria", "Gerald", "Teresa", "Carl", "Ann", "Harold", "Sara", "Dylan",
    "Madison", "Arthur", "Frances", "Lawrence", "Kathryn", "Jordan",
    "Janice", "Jesse", "Jean", "Bryan", "Abigail", "Billy", "Alice",
    "Bruce", "Judy", "Gabriel", "Sophia", "Joe", "Grace", "Logan", "Denise",
    "Albert", "Amber", "Willie", "Doris", "Alan", "Marilyn", "Eugene",
    "Danielle", "Russell", "Beverly", "Vincent", "Isabella", "Philip",
    "Theresa", "Bobby", "Diana", "Johnny", "Natalie", "Bradley", "Brittany",
    # International names
    "Wei", "Yuki", "Raj", "Priya", "Ahmed", "Fatima", "Carlos", "Sofia",
    "Hiroshi", "Mei", "Amir", "Leila", "Sven", "Ingrid", "Dmitri", "Olga",
    "Chen", "Akiko", "Vikram", "Ananya", "Omar", "Nadia", "Luis", "Carmen",
    "Kenji", "Hana", "Ravi", "Deepa", "Hassan", "Zahra", "Klaus", "Astrid",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
    "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
    "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green",
    "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz",
    "Parker", "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris",
    "Morales", "Murphy", "Cook", "Rogers", "Gutierrez", "Ortiz", "Morgan",
    "Cooper", "Peterson", "Bailey", "Reed", "Kelly", "Howard", "Ramos",
    "Kim", "Cox", "Ward", "Richardson", "Watson", "Brooks", "Chavez",
    "Wood", "James", "Bennett", "Gray", "Mendoza", "Ruiz", "Hughes",
    "Price", "Alvarez", "Castillo", "Sanders", "Patel", "Myers", "Long",
    "Ross", "Foster", "Jimenez", "Powell", "Jenkins", "Perry", "Russell",
    "Sullivan", "Bell", "Coleman", "Butler", "Henderson", "Barnes",
    "Gonzales", "Fisher", "Vasquez", "Simmons", "Griffin", "Aguilar",
    "Wallace", "Hamilton", "Stone", "Hayes", "West", "Cole", "Hunt",
    "Gibson", "Bryant", "Ellis", "Stevens", "Murray", "Ford", "Marshall",
    "Owens", "McDonald", "Harrison", "Rubin", "Kennedy", "Wells", "Alvarez",
    "Woods", "Mendez", "Fox", "Jordan", "Byrd", "Mills", "Burns",
    "Hartman", "Wolfe", "Bishop", "Reeves", "Chambers", "Dorsey", "Mack",
    "Howell", "Moran", "Garrett", "Lane", "Hicks", "Armstrong", "Lambert",
    "Dunn", "Crawford", "Brady", "Weber", "Fields", "Weaver", "Barker",
    "Bates", "Pearson", "Horton", "Stokes", "Day", "Floyd", "Keller",
    "Drake", "Mann", "Logan", "Werner", "Schwartz", "Larson", "Hanson",
    "Olson", "Lindberg", "Stein", "Becker", "Schultz", "Fischer", "Meyer",
    "Schneider", "Wagner", "Hoffman", "Mueller", "Koch", "Bauer", "Richter",
    "Klein", "Wolf", "Neumann", "Zimmermann", "Krause", "Braun", "Lehmann",
    "Schmitt", "Hartmann", "Krueger", "Lange", "Werner", "Meier", "Kramer",
    "Huber", "Kaiser", "Fuchs", "Scholz", "Schreiber", "Tanaka", "Yamamoto",
    "Nakamura", "Watanabe", "Ito", "Suzuki", "Takahashi", "Sato", "Kumar",
    "Singh", "Sharma", "Gupta", "Chen", "Wang", "Zhang", "Liu", "Yang",
    "Huang", "Zhao", "Wu", "Zhou", "Xu", "Park", "Choi", "Kang", "Cho",
    "Yoon", "Jang", "Fernandez", "Moreno", "Romero", "Alonso", "Navarro",
    "Dominguez", "Vazquez", "Ramos", "Serrano", "Molina", "Blanco",
    "Suarez", "Sanz", "Castro", "Delgado", "Prieto", "Medina", "Vega",
    "Herrero", "Lorenzo",
]

DEPARTMENTS = [
    "Engineering", "Sales", "Marketing", "Human Resources", "Finance",
    "Legal", "IT", "Operations", "Product", "Design", "Customer Success",
    "Security", "Data Science", "DevOps", "QA", "Support", "Research",
    "Compliance", "Facilities", "Procurement", "Communications", "Strategy",
    "Analytics", "Training", "Executive", "Business Development",
    "Supply Chain", "Internal Audit", "Risk Management", "Investor Relations",
]

# Map departments to divisions
DEPT_TO_DIVISION = {
    "Engineering": "Technology",
    "DevOps": "Technology",
    "QA": "Technology",
    "IT": "Technology",
    "Data Science": "Technology",
    "Security": "Technology",
    "Sales": "Revenue",
    "Business Development": "Revenue",
    "Marketing": "Revenue",
    "Customer Success": "Revenue",
    "Finance": "Corporate",
    "Legal": "Corporate",
    "Compliance": "Corporate",
    "Internal Audit": "Corporate",
    "Risk Management": "Corporate",
    "Investor Relations": "Corporate",
    "Human Resources": "People",
    "Training": "People",
    "Operations": "Operations",
    "Supply Chain": "Operations",
    "Facilities": "Operations",
    "Procurement": "Operations",
    "Product": "Product",
    "Design": "Product",
    "Research": "Product",
    "Support": "Services",
    "Communications": "Corporate",
    "Strategy": "Executive",
    "Analytics": "Technology",
    "Executive": "Executive",
}

# Department-appropriate job titles (roughly 50 unique titles, many shared)
DEPT_TITLES = {
    "Engineering": [
        "Software Engineer", "Senior Software Engineer", "Staff Engineer",
        "Principal Engineer", "Engineering Manager", "Tech Lead",
        "Backend Developer", "Frontend Developer", "Full Stack Developer",
        "Architect",
    ],
    "Sales": [
        "Account Executive", "Sales Representative", "Sales Manager",
        "Regional Sales Director", "Sales Engineer", "Inside Sales Rep",
        "Enterprise Account Manager", "Sales Analyst",
    ],
    "Marketing": [
        "Marketing Manager", "Content Strategist", "SEO Specialist",
        "Digital Marketing Manager", "Brand Manager", "Marketing Analyst",
        "Campaign Manager", "Growth Manager",
    ],
    "Human Resources": [
        "HR Generalist", "HR Manager", "Recruiter", "Senior Recruiter",
        "Talent Acquisition Lead", "HR Business Partner",
        "Compensation Analyst", "Benefits Coordinator",
    ],
    "Finance": [
        "Financial Analyst", "Senior Accountant", "Controller",
        "FP&A Manager", "Accounts Payable Specialist", "Treasury Analyst",
        "Revenue Analyst", "Finance Manager",
    ],
    "Legal": [
        "Corporate Counsel", "Legal Counsel", "Paralegal",
        "General Counsel", "Contract Specialist", "IP Attorney",
        "Compliance Attorney",
    ],
    "IT": [
        "Systems Administrator", "Network Engineer", "IT Manager",
        "Help Desk Analyst", "IT Support Specialist",
        "Infrastructure Engineer", "Cloud Engineer", "IT Director",
    ],
    "Operations": [
        "Operations Manager", "Operations Analyst", "Process Engineer",
        "Project Manager", "Program Manager", "Operations Director",
        "Business Analyst",
    ],
    "Product": [
        "Product Manager", "Senior Product Manager", "Product Owner",
        "Product Analyst", "Director of Product", "Technical Product Manager",
    ],
    "Design": [
        "UX Designer", "UI Designer", "Senior Designer",
        "Design Manager", "Visual Designer", "UX Researcher",
        "Interaction Designer",
    ],
    "Customer Success": [
        "Customer Success Manager", "CSM Lead", "Onboarding Specialist",
        "Customer Success Director", "Renewals Manager",
        "Customer Experience Analyst",
    ],
    "Security": [
        "Security Engineer", "Security Analyst", "CISO",
        "Penetration Tester", "SOC Analyst", "Security Architect",
        "GRC Analyst",
    ],
    "Data Science": [
        "Data Scientist", "Senior Data Scientist", "ML Engineer",
        "Data Engineer", "Analytics Engineer", "Research Scientist",
    ],
    "DevOps": [
        "DevOps Engineer", "Site Reliability Engineer", "SRE Manager",
        "Platform Engineer", "Release Engineer", "Build Engineer",
    ],
    "QA": [
        "QA Engineer", "Senior QA Engineer", "QA Lead",
        "Test Automation Engineer", "QA Manager", "SDET",
    ],
    "Support": [
        "Support Engineer", "Technical Support Specialist",
        "Support Manager", "Escalation Engineer", "Support Analyst",
    ],
    "Research": [
        "Research Scientist", "Senior Researcher", "Research Director",
        "Lab Manager", "Research Analyst", "Research Fellow",
    ],
    "Compliance": [
        "Compliance Officer", "Compliance Analyst", "Compliance Manager",
        "Regulatory Specialist", "Audit Analyst",
    ],
    "Facilities": [
        "Facilities Manager", "Facilities Coordinator",
        "Maintenance Technician", "Office Manager", "Space Planner",
    ],
    "Procurement": [
        "Procurement Manager", "Buyer", "Senior Buyer",
        "Procurement Analyst", "Vendor Manager", "Sourcing Specialist",
    ],
    "Communications": [
        "Communications Manager", "PR Specialist", "Internal Comms Lead",
        "Corporate Communications Director", "Media Relations Manager",
    ],
    "Strategy": [
        "Strategy Analyst", "Chief Strategy Officer", "Strategy Director",
        "Business Strategy Manager", "Corporate Development Analyst",
    ],
    "Analytics": [
        "Analytics Engineer", "Business Intelligence Analyst",
        "Data Analyst", "Senior Analyst", "Analytics Manager",
    ],
    "Training": [
        "Training Manager", "Learning Designer",
        "Training Coordinator", "L&D Specialist", "Instructional Designer",
    ],
    "Executive": [
        "CEO", "COO", "CFO", "CTO", "CMO", "VP of Engineering",
        "VP of Sales", "VP of Marketing", "Chief of Staff",
    ],
    "Business Development": [
        "BD Manager", "BD Representative", "Partnerships Manager",
        "Alliance Manager", "BD Director", "Strategic Partnerships Lead",
    ],
    "Supply Chain": [
        "Supply Chain Manager", "Logistics Coordinator",
        "Supply Chain Analyst", "Inventory Manager", "Distribution Manager",
    ],
    "Internal Audit": [
        "Internal Auditor", "Senior Auditor", "Audit Manager",
        "IT Auditor", "Audit Director",
    ],
    "Risk Management": [
        "Risk Analyst", "Risk Manager", "Senior Risk Analyst",
        "ERM Specialist", "Risk Director",
    ],
    "Investor Relations": [
        "IR Manager", "IR Analyst", "VP of Investor Relations",
        "IR Coordinator", "IR Director",
    ],
}

EMAIL_DOMAINS = [
    "acme-corp.com", "globex-industries.net", "initech.io", "contoso.com",
    "fabrikam.org", "northwind-trading.com", "waystar-royco.com",
    "sterling-cooper.com", "dunder-mifflin.com", "hooli.com",
    "pied-piper.net", "massive-dynamic.com", "umbrella-corp.com",
    "wayne-enterprises.com", "stark-industries.com", "cyberdyne-systems.com",
    "oscorp.io", "lexcorp.com", "aperture-science.net", "weyland-yutani.com",
]

OFFICE_LOCATIONS = [
    "New York", "London", "Singapore", "San Francisco", "Chicago",
    "Austin", "Seattle", "Boston", "Denver", "Atlanta",
    "Toronto", "Dublin", "Sydney", "Tokyo", "Berlin",
]

# Short codes for cost center generation
_DEPT_CODES = {d: d[:3].upper() for d in DEPARTMENTS}
_OFFICE_CODES = {loc: loc[:3].upper() for loc in OFFICE_LOCATIONS}

# Status distribution: Active 85%, On Leave 10%, Terminated 5%
_STATUS_WEIGHTS = ["Active"] * 85 + ["On Leave"] * 10 + ["Terminated"] * 5

# Date range for Start Date
_START_DATE_MIN = date(2015, 1, 1)
_START_DATE_MAX = date(2026, 3, 1)
_DATE_RANGE_DAYS = (_START_DATE_MAX - _START_DATE_MIN).days

# CSV column header order
COLUMNS = [
    "Email", "First Name", "Last Name", "Department", "Title", "Office",
    "Phone", "Employee ID", "Manager", "Division", "Cost Center", "Location",
    "Start Date", "Status", "Custom1",
]

# Tier definitions: name -> row count
TIERS = {
    "10k": 10_000,
    "50k": 50_000,
    "100k": 100_000,
    "300k": 300_000,
    "400k": 400_000,
}


# ---------------------------------------------------------------------------
# Row generator
# ---------------------------------------------------------------------------

def _random_phone(rng: random.Random) -> str:
    """Generate a phone number in +1-555-XXXXXXX format."""
    digits = "".join(rng.choices(string.digits, k=7))
    return f"+1-555-{digits}"


def _random_project_code(rng: random.Random) -> str:
    """Generate a project code like PRJ-ABCD."""
    chars = "".join(rng.choices(string.ascii_uppercase + string.digits, k=4))
    return f"PRJ-{chars}"


def _random_date(rng: random.Random) -> str:
    """Generate a random date between 2015-01-01 and 2026-03-01."""
    offset = rng.randint(0, _DATE_RANGE_DAYS)
    d = _START_DATE_MIN + timedelta(days=offset)
    return d.isoformat()


def generate_rows(count: int, seed: int = 42):
    """Yield `count` rows as lists of strings.

    Uses deterministic seeding for reproducibility. Each row has 15 columns
    matching the COLUMNS header list.
    """
    rng = random.Random(seed)

    # Pre-generate a pool of manager names (pick from first 5000 or count,
    # whichever is smaller, to keep manager references realistic).
    manager_pool_size = min(count, 5000)
    manager_names = []
    manager_rng = random.Random(seed)
    for _ in range(manager_pool_size):
        fn = manager_rng.choice(FIRST_NAMES)
        ln = manager_rng.choice(LAST_NAMES)
        manager_names.append(f"{fn} {ln}")

    for i in range(count):
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        domain = rng.choice(EMAIL_DOMAINS)
        email = f"{first.lower()}.{last.lower()}{i}@{domain}"

        dept = rng.choice(DEPARTMENTS)
        titles = DEPT_TITLES.get(dept, ["Specialist"])
        title = rng.choice(titles)

        office = rng.choice(OFFICE_LOCATIONS)
        phone = _random_phone(rng)
        emp_id = f"EMP-{i:06d}"
        manager = rng.choice(manager_names)
        division = DEPT_TO_DIVISION.get(dept, "General")
        cost_center = f"CC-{_DEPT_CODES[dept]}-{_OFFICE_CODES[office]}"
        location = office
        start_date = _random_date(rng)
        status = rng.choice(_STATUS_WEIGHTS)
        custom1 = _random_project_code(rng)

        yield [
            email, first, last, dept, title, office, phone, emp_id,
            manager, division, cost_center, location, start_date,
            status, custom1,
        ]


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def write_csv(path: str, count: int, seed: int) -> None:
    """Write a CSV file with streaming csv.writer (low memory)."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for row in generate_rows(count, seed):
            writer.writerow(row)


def write_xlsx(path: str, count: int, seed: int) -> None:
    """Write an XLSX file using openpyxl write_only mode (critical for large files)."""
    try:
        from openpyxl import Workbook
    except ImportError:
        print("ERROR: openpyxl is required for XLSX generation.", file=sys.stderr)
        print("Install it with: pip install openpyxl", file=sys.stderr)
        sys.exit(1)

    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Contacts")
    ws.append(COLUMNS)
    for row in generate_rows(count, seed):
        ws.append(row)
    wb.save(path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _file_size_str(path: str) -> str:
    """Return human-readable file size."""
    size = os.path.getsize(path)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate realistic test address book files for TidePool benchmarking. "
            "Produces CSV and XLSX files at configurable size tiers (10K-400K rows) "
            "with deterministic seeding for reproducible results."
        ),
    )
    parser.add_argument(
        "--tiers",
        type=str,
        default=",".join(TIERS.keys()),
        help=(
            "Comma-separated list of size tiers to generate. "
            f"Available: {', '.join(TIERS.keys())}. Default: all tiers."
        ),
    )
    parser.add_argument(
        "--formats",
        type=str,
        default="both",
        choices=["csv", "xlsx", "both"],
        help="Output format(s) to generate. Default: both.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data"),
        help="Directory to write generated files. Default: scripts/test_data/",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic generation. Default: 42.",
    )
    args = parser.parse_args()

    # Parse tiers
    requested = [t.strip().lower() for t in args.tiers.split(",")]
    for t in requested:
        if t not in TIERS:
            parser.error(f"Unknown tier: {t!r}. Available: {', '.join(TIERS.keys())}")

    # Parse formats
    do_csv = args.formats in ("csv", "both")
    do_xlsx = args.formats in ("xlsx", "both")

    # Ensure output directory exists
    os.makedirs(args.output_dir, exist_ok=True)

    print(f"Output directory : {args.output_dir}")
    print(f"Seed             : {args.seed}")
    print(f"Tiers            : {', '.join(requested)}")
    print(f"Formats          : {args.formats}")
    print("-" * 60)

    for tier_name in requested:
        row_count = TIERS[tier_name]
        print(f"\n[{tier_name.upper()}] Generating {row_count:,} rows...")

        if do_csv:
            csv_path = os.path.join(args.output_dir, f"addressbook_{tier_name}.csv")
            t0 = time.perf_counter()
            write_csv(csv_path, row_count, args.seed)
            elapsed = time.perf_counter() - t0
            size = _file_size_str(csv_path)
            print(f"  CSV  : {csv_path}")
            print(f"         {size} in {elapsed:.2f}s")

        if do_xlsx:
            xlsx_path = os.path.join(args.output_dir, f"addressbook_{tier_name}.xlsx")
            t0 = time.perf_counter()
            write_xlsx(xlsx_path, row_count, args.seed)
            elapsed = time.perf_counter() - t0
            size = _file_size_str(xlsx_path)
            print(f"  XLSX : {xlsx_path}")
            print(f"         {size} in {elapsed:.2f}s")

    print("\n" + "-" * 60)
    print("Done.")


if __name__ == "__main__":
    main()
