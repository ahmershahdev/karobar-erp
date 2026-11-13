"""Invented businesses for the demo. Every name, number and ID here is made up."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

D = Decimal


@dataclass(frozen=True)
class Item:
    sku: str
    name: str
    category: str
    cost: Decimal
    price: Decimal
    # Pieces in a carton, or 0 for an item only sold loose.
    carton: int = 0
    # Tracked by batch and expiry date.
    batches: bool = False


@dataclass(frozen=True)
class Party:
    code: str
    name: str
    terms: int = 0
    phone: str = ""


@dataclass(frozen=True)
class Person:
    code: str
    name: str
    title: str
    department: str
    basic: Decimal
    joined: date
    nationality: str = ""
    housing: Decimal = Decimal(0)


@dataclass(frozen=True)
class Plan:
    kind: str
    name: str
    currency: str
    locale: str
    fiscal_month: int
    valuation: str
    country: str
    weekend: list[int]
    province: str
    tax_name: str
    tax_percent: Decimal
    tax_from: date
    tax_source: str
    sales_a_day: tuple[int, int]
    items: list[Item]
    customers: list[Party]
    suppliers: list[Party]
    landlord: Party
    utility: Party
    rent: Decimal
    power: tuple[int, int]
    people: list[Person]
    wps_employer_id: str = ""
    wps_bank_code: str = ""
    # Contribution rates entered for the demo: (scheme, employer %, employee %, options).
    rates: list[tuple[str, Decimal, Decimal, dict[str, object]]] = field(default_factory=list)
    rates_source: str = ""


WALK_IN = Party("WALKIN", "Walk-in customer")

PAKISTAN = Plan(
    kind="pk",
    name="Noor Kiryana Store (demo)",
    currency="PKR",
    locale="ur",
    fiscal_month=7,
    valuation="average",
    country="PK",
    weekend=[6],
    province="SD",
    tax_name="Sales tax",
    tax_percent=D(18),
    tax_from=date(2024, 7, 1),
    tax_source="Sales Tax Act 1990, section 3: standard rate of 18% (demo business).",
    sales_a_day=(4, 10),
    items=[
        Item("RICE-5", "Basmati rice 5 kg", "Grocery", D(1650), D(1900), 4),
        Item("ATTA-10", "Chakki atta 10 kg", "Grocery", D(1180), D(1350), 2),
        Item("SUGAR-1", "Sugar 1 kg", "Grocery", D(145), D(165), 10),
        Item("DAAL-M", "Daal masoor 1 kg", "Grocery", D(290), D(340), 10),
        Item("DAAL-C", "Daal chana 1 kg", "Grocery", D(250), D(300), 10),
        Item("BESAN-1", "Besan 1 kg", "Grocery", D(260), D(310), 10),
        Item("SALT-800", "Iodised salt 800 g", "Grocery", D(48), D(60), 24),
        Item("OIL-5", "Cooking oil 5 litre", "Grocery", D(2350), D(2650), 4),
        Item("GHEE-1", "Banaspati ghee 1 kg", "Grocery", D(520), D(590), 12),
        Item("TEA-475", "Black tea 475 g", "Beverages", D(820), D(950), 12),
        Item("TEA-95", "Black tea 95 g", "Beverages", D(175), D(210), 48),
        Item("MILK-P", "Milk powder 390 g", "Dairy", D(890), D(1020), 12, True),
        Item("MILK-1", "Packed milk 1 litre", "Dairy", D(255), D(290), 12, True),
        Item("YOG-1", "Yogurt 1 kg", "Dairy", D(240), D(280), 0, True),
        Item("SPICE-CH", "Red chilli powder 200 g", "Spices", D(210), D(260), 24),
        Item("SPICE-HD", "Turmeric powder 200 g", "Spices", D(170), D(210), 24),
        Item("SPICE-BM", "Biryani masala 50 g", "Spices", D(95), D(120), 48),
        Item("SPICE-GM", "Garam masala 100 g", "Spices", D(150), D(190), 24),
        Item("BISC-T", "Tea biscuits family pack", "Snacks", D(165), D(200), 24),
        Item("BISC-C", "Cream biscuits half roll", "Snacks", D(45), D(60), 48),
        Item("CHIPS-L", "Potato chips large", "Snacks", D(85), D(110), 36),
        Item("NIMKO-1", "Mix nimko 250 g", "Snacks", D(130), D(170), 24),
        Item("DRINK-15", "Cola 1.5 litre", "Beverages", D(150), D(180), 6),
        Item("DRINK-50", "Cola 500 ml", "Beverages", D(75), D(95), 12),
        Item("WATER-15", "Mineral water 1.5 litre", "Beverages", D(70), D(90), 6),
        Item("JUICE-1", "Mango juice 1 litre", "Beverages", D(210), D(250), 12),
        Item("SOAP-B", "Bath soap 115 g", "Personal care", D(105), D(130), 48),
        Item("SHAMP-S", "Shampoo 185 ml", "Personal care", D(430), D(510), 24),
        Item("PASTE-T", "Toothpaste 100 g", "Personal care", D(240), D(290), 36),
        Item("BRUSH-T", "Toothbrush medium", "Personal care", D(85), D(120), 48),
        Item("DET-1", "Washing powder 1 kg", "Household", D(460), D(540), 12),
        Item("DISH-L", "Dishwash bar large", "Household", D(110), D(140), 24),
        Item("BLEACH-1", "Bleach 1 litre", "Household", D(190), D(240), 12),
        Item("TISSUE-B", "Tissue box", "Household", D(145), D(185), 24),
        Item("MATCH-10", "Matchboxes pack of 10", "Household", D(55), D(70), 50),
        Item("EGG-12", "Eggs dozen", "Fresh", D(330), D(380)),
        Item("BREAD-L", "Bread large", "Fresh", D(160), D(190), 0, True),
        Item("RUSK-1", "Rusk 400 g", "Bakery", D(190), D(230), 12),
        Item("NOODLE-1", "Instant noodles", "Snacks", D(52), D(65), 24),
        Item("KETCH-8", "Ketchup 800 g", "Grocery", D(380), D(450), 12),
    ],
    customers=[
        WALK_IN,
        Party("C001", "Al-Madina Hotel", 15, "0300-0000101"),
        Party("C002", "Bismillah Tea Stall", 7, "0300-0000102"),
        Party("C003", "Hyderabad Canteen Services", 30, "0300-0000103"),
        Party("C004", "Qasimabad Boys Hostel", 30, "0300-0000104"),
        Party("C005", "Latifabad Corner Shop", 15, "0300-0000105"),
        Party("C006", "Sunrise School Tuck Shop", 30, "0300-0000106"),
        Party("C007", "Mehran Office Pantry", 15, "0300-0000107"),
        Party("C008", "Hirabad General Store", 15, "0300-0000108"),
        Party("C009", "Green Valley Guest House", 30, "0300-0000109"),
        Party("C010", "Khan Fast Food", 7, "0300-0000110"),
        Party("C011", "Paradise Bakers", 15, "0300-0000111"),
        Party("C012", "City Clinic Staff Room", 30, "0300-0000112"),
        Party("C013", "Riverside Restaurant", 15, "0300-0000113"),
        Party("C014", "Station Road Dhaba", 7, "0300-0000114"),
    ],
    suppliers=[
        Party("S001", "Indus Grain Distributors", 15, "022-0000201"),
        Party("S002", "Sindh Edible Oils", 30, "022-0000202"),
        Party("S003", "Kotri Dairy Supplies", 7, "022-0000203"),
        Party("S004", "Karachi Spice House", 30, "021-0000204"),
        Party("S005", "Pak Snacks Wholesale", 15, "021-0000205"),
        Party("S006", "Bottlers Hyderabad", 15, "022-0000206"),
        Party("S007", "Clean Home Traders", 30, "021-0000207"),
        Party("S008", "Fresh Farm Eggs and Bakery", 7, "022-0000208"),
    ],
    landlord=Party("S101", "Qureshi Properties", 0),
    utility=Party("S102", "City Electric Supply", 0),
    rent=D(85000),
    power=(28000, 46000),
    people=[
        Person("E001", "Ahmed Raza", "Store manager", "Shop floor", D(95000), date(2023, 3, 1)),
        Person("E002", "Bilal Shaikh", "Cashier", "Shop floor", D(48000), date(2024, 1, 15)),
        Person("E003", "Sana Memon", "Cashier", "Shop floor", D(46000), date(2024, 8, 1)),
        Person("E004", "Imran Soomro", "Store keeper", "Store room", D(44000), date(2023, 9, 1)),
        Person(
            "E005", "Kashif Abbasi", "Delivery rider", "Store room", D(40000), date(2025, 2, 1)
        ),
        Person("E006", "Nadia Qazi", "Accountant", "Office", D(85000), date(2023, 6, 1)),
    ],
    rates=[("eobi", D(5), D(1), {"on_minimum_wage": True})],
    rates_source=(
        "Invented for the demo, not an official figure. Enter your own rates from your EOBI "
        "challan or notification."
    ),
)

UAE = Plan(
    kind="ae",
    name="Al Waha General Trading (demo)",
    currency="AED",
    locale="ar",
    fiscal_month=1,
    valuation="fifo",
    country="AE",
    weekend=[5, 6],
    province="",
    tax_name="VAT",
    tax_percent=D(5),
    tax_from=date(2018, 1, 1),
    tax_source="Federal Decree-Law No. 8 of 2017 on VAT, Article 3: standard rate (demo).",
    sales_a_day=(9, 18),
    items=[
        Item("RICE-10", "Basmati rice 10 kg", "Grocery", D(52), D(65), 2),
        Item("FLOUR-5", "Chakki flour 5 kg", "Grocery", D(15), D(19), 4),
        Item("SUGAR-2", "Sugar 2 kg", "Grocery", D(8), D("10.5"), 10),
        Item("LENTIL-1", "Red lentils 1 kg", "Grocery", D("6.5"), D("8.5"), 10),
        Item("CHICK-1", "Chickpeas 1 kg", "Grocery", D(7), D(9), 10),
        Item("OIL-18", "Sunflower oil 1.8 litre", "Grocery", D(13), D("16.5"), 6),
        Item("GHEE-16", "Vegetable ghee 1.6 kg", "Grocery", D(24), D(29), 6),
        Item("PASTA-5", "Spaghetti 500 g", "Grocery", D("3.2"), D("4.5"), 20),
        Item("TOMP-1", "Tomato paste 400 g", "Grocery", D(3), D("4.25"), 24),
        Item("TUNA-3", "Tuna in oil pack of 3", "Grocery", D(11), D(14), 16),
        Item("TEA-450", "Black tea 450 g", "Beverages", D(14), D(18), 12),
        Item("COFF-200", "Arabic coffee 200 g", "Beverages", D(17), D(22), 12),
        Item("DATES-1", "Dates 1 kg box", "Grocery", D(18), D(25), 10),
        Item("MILK-2", "Fresh milk 2 litre", "Dairy", D("8.5"), D("10.5"), 6, True),
        Item("LABAN-1", "Laban 1 litre", "Dairy", D("4.5"), D("5.75"), 12, True),
        Item("CHEESE-S", "Cheese slices 200 g", "Dairy", D("7.5"), D("9.75"), 12, True),
        Item("YOG-500", "Yogurt 500 g", "Dairy", D(4), D("5.25"), 12, True),
        Item("EGG-30", "Eggs tray of 30", "Fresh", D(16), D("19.5")),
        Item("BREAD-A", "Arabic bread pack", "Bakery", D("2.5"), D("3.5"), 0, True),
        Item("WATER-12", "Water 500 ml pack of 12", "Beverages", D("5.5"), D("7.5"), 2),
        Item("WATER-5G", "Water 5 gallon", "Beverages", D(9), D(12)),
        Item("SODA-6", "Soft drink cans pack of 6", "Beverages", D("9.5"), D("12.5"), 4),
        Item("JUICE-1L", "Orange juice 1 litre", "Beverages", D(6), D(8), 12),
        Item("CHIPS-B", "Potato chips 150 g", "Snacks", D(4), D("5.5"), 24),
        Item("BISC-D", "Digestive biscuits 400 g", "Snacks", D("6.5"), D("8.5"), 12),
        Item("CHOC-B", "Chocolate bar", "Snacks", D("2.2"), D(3), 48),
        Item("NUTS-500", "Mixed nuts 500 g", "Snacks", D(22), D(29), 12),
        Item("SOAP-4", "Hand soap pack of 4", "Personal care", D(8), D(11), 12),
        Item("SHAMP-4", "Shampoo 400 ml", "Personal care", D(13), D("17.5"), 12),
        Item("PASTE-1", "Toothpaste 120 ml", "Personal care", D("6.5"), D("8.75"), 24),
        Item("DEO-1", "Deodorant 150 ml", "Personal care", D(9), D("12.5"), 12),
        Item("TISS-5", "Facial tissues pack of 5", "Household", D(9), D(12), 8),
        Item("DET-3", "Laundry detergent 3 kg", "Household", D(21), D(27), 4),
        Item("DISH-1", "Dishwashing liquid 1 litre", "Household", D(6), D(8), 12),
        Item("CLEAN-1", "Floor cleaner 1 litre", "Household", D(7), D("9.5"), 12),
        Item("FOIL-1", "Aluminium foil roll", "Household", D("5.5"), D("7.5"), 24),
        Item("BAGS-50", "Garbage bags roll of 50", "Household", D(6), D("8.5"), 20),
        Item("CHAR-1", "Charcoal 3 kg", "Household", D(12), D(16), 6),
        Item("GAS-C", "Camping gas cartridge", "Household", D("4.5"), D("6.5"), 24),
        Item("BATT-AA", "AA batteries pack of 4", "Household", D(7), D(10), 24),
    ],
    customers=[
        WALK_IN,
        Party("C001", "Marina Tower Cafeteria", 30, "04-000-0101"),
        Party("C002", "Deira Labour Camp Kitchen", 30, "04-000-0102"),
        Party("C003", "Al Barsha Villa Services", 15, "04-000-0103"),
        Party("C004", "Karama Office Supplies", 30, "04-000-0104"),
        Party("C005", "JLT Coffee Corner", 15, "04-000-0105"),
        Party("C006", "Bur Dubai Tailoring Shop", 15, "04-000-0106"),
        Party("C007", "Silicon Oasis Clinic", 30, "04-000-0107"),
        Party("C008", "Al Quoz Workshop Canteen", 30, "04-000-0108"),
        Party("C009", "Mirdif Nursery", 30, "04-000-0109"),
        Party("C010", "Satwa Barber Lounge", 15, "04-000-0110"),
        Party("C011", "Business Bay Pantry Co", 30, "04-000-0111"),
        Party("C012", "Oud Metha Guest House", 15, "04-000-0112"),
        Party("C013", "Al Nahda Salon", 15, "04-000-0113"),
        Party("C014", "Jebel Ali Site Office", 30, "04-000-0114"),
    ],
    suppliers=[
        Party("S001", "Gulf Grains Trading", 30, "04-000-0201"),
        Party("S002", "Emirates Edible Oils", 30, "04-000-0202"),
        Party("S003", "Oasis Dairy Distribution", 7, "04-000-0203"),
        Party("S004", "Arabian Beverages Supply", 15, "04-000-0204"),
        Party("S005", "Creek Snacks Wholesale", 15, "04-000-0205"),
        Party("S006", "Desert Home Care", 30, "04-000-0206"),
        Party("S007", "Al Khail Bakery", 7, "04-000-0207"),
        Party("S008", "Harbour Household Imports", 30, "04-000-0208"),
    ],
    landlord=Party("S101", "Al Fahidi Real Estate", 0),
    utility=Party("S102", "Metro Utilities Billing", 0),
    rent=D(9500),
    power=(1400, 2600),
    people=[
        Person(
            "E001",
            "Rashid Al Mansoori",
            "General manager",
            "Office",
            D(12000),
            date(2021, 4, 1),
            "AE",
            D(4000),
        ),
        Person(
            "E002",
            "Faisal Khan",
            "Store supervisor",
            "Shop floor",
            D(4500),
            date(2022, 2, 1),
            "PK",
            D(1500),
        ),
        Person(
            "E003",
            "Maria Santos",
            "Cashier",
            "Shop floor",
            D(2800),
            date(2023, 5, 15),
            "PH",
            D(800),
        ),
        Person(
            "E004",
            "Arjun Nair",
            "Accountant",
            "Office",
            D(5000),
            date(2022, 9, 1),
            "IN",
            D(1500),
        ),
        Person(
            "E005",
            "Samir Haddad",
            "Delivery driver",
            "Store room",
            D(2500),
            date(2024, 1, 10),
            "EG",
            D(700),
        ),
        Person(
            "E006",
            "Joseph Mensah",
            "Store keeper",
            "Store room",
            D(2200),
            date(2025, 3, 1),
            "GH",
            D(600),
        ),
    ],
    wps_employer_id="0000000123456",
    wps_bank_code="000000001",
    rates=[("gpssa", D("12.5"), D(5), {"on_insurable": True, "applies_to": "nationals"})],
    rates_source=(
        "Invented for the demo, not an official figure. Enter your own rates from your GPSSA "
        "statement."
    ),
)

PLANS = {"pk": PAKISTAN, "ae": UAE}

# Labour card person IDs (14 digits) and routing codes (9 digits), all invented.
WPS_AGENT = "000000002"


def barcode(kind: str, number: int) -> str:
    """An EAN-13 in the 20 to 29 range, which GS1 keeps for a shop's own use, so it can never
    be a real product's code."""
    body = f"2{'1' if kind == 'pk' else '2'}{number:010d}"
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(body))
    return body + str((10 - total % 10) % 10)
