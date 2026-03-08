"""V-Dem (Varieties of Democracy) local dataset adapter.

Provides access to the V-Dem Country-Year Full+Others v15 dataset,
which is bundled locally (not available via API). Searches a curated
index of key indicators and extracts relevant column subsets as CSV.

License: CC-BY-SA. Citation required — see CITATION below.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from app.schemas.datasets import DatasetResult
from app.services.sources.base import extract_keywords as _extract_keywords

logger = logging.getLogger(__name__)

CITATION = (
    "Coppedge, Michael, John Gerring, Carl Henrik Knutsen, Staffan I. Lindberg, "
    'Jan Teorell, et al. 2025. "V-Dem [Country-Year/Country-Date] Dataset v15" '
    "Varieties of Democracy (V-Dem) Project. https://doi.org/10.23696/vdemds25"
)

# Path to the bundled CSV — relative to the repo root
_DATA_DIR = Path(__file__).resolve().parents[4] / "V-Dem-CY-FullOthers-v15_csv"
_CSV_FILE = _DATA_DIR / "V-Dem-CY-Full+Others-v15.csv"

# Identity columns always included in extracts
_ID_COLS = ["country_name", "country_text_id", "year"]

# Curated indicator groups with human-readable descriptions.
# Each entry: (dataset_id, title, description, columns)
_INDICATOR_GROUPS: list[tuple[str, str, str, list[str]]] = [
    (
        "vdem_electoral_democracy",
        "Electoral Democracy Index",
        "Composite index measuring electoral democracy: free and fair elections, "
        "freedom of expression, associational autonomy, inclusive suffrage, and elected officials.",
        [
            "v2x_polyarchy",
            "v2x_api",
            "v2x_mpi",
            "v2x_freexp_altinf",
            "v2x_frassoc_thick",
            "v2x_suffr",
            "v2xel_frefair",
            "v2x_elecoff",
        ],
    ),
    (
        "vdem_liberal_democracy",
        "Liberal Democracy Index",
        "Measures liberal democracy: rule of law, judicial constraints on executive, "
        "legislative constraints on executive, and individual liberties protection.",
        ["v2x_libdem", "v2x_liberal", "v2xcl_rol", "v2x_jucon", "v2xlg_legcon"],
    ),
    (
        "vdem_participatory_democracy",
        "Participatory Democracy Index",
        "Civil society participation, direct democracy mechanisms, local and regional "
        "elections, and citizen engagement in governance.",
        ["v2x_partipdem", "v2x_partip", "v2x_cspart", "v2xdd_dd", "v2xel_locelec", "v2xel_regelec"],
    ),
    (
        "vdem_deliberative_democracy",
        "Deliberative Democracy Index",
        "Quality of public deliberation: reasoned justification, common good orientation, "
        "respect for counterarguments, range of consultation, and engaged society.",
        ["v2x_delibdem", "v2xdl_delib"],
    ),
    (
        "vdem_egalitarian_democracy",
        "Egalitarian Democracy Index",
        "Equal protection, equal access to power, equal distribution of resources, "
        "health equality, and educational equality across social groups.",
        ["v2x_egaldem", "v2x_egal", "v2xeg_eqprotec", "v2xeg_eqaccess", "v2xeg_eqdr"],
    ),
    (
        "vdem_civil_liberties",
        "Civil Liberties and Human Rights",
        "Freedom of expression, media freedom, academic freedom, freedom of religion, "
        "freedom of movement, political killings, torture, and civil liberty index.",
        [
            "v2x_clpol",
            "v2x_clpriv",
            "v2xcl_disc",
            "v2xcl_dmove",
            "v2xcl_slave",
            "v2cltort",
            "v2clkill",
            "v2clfree",
            "v2clrelig",
            "v2clacfree",
            "v2meaccess",
            "v2mebias",
            "v2mecenefm",
            "v2mecrit",
            "v2meharjrn",
        ],
    ),
    (
        "vdem_corruption",
        "Political Corruption Index",
        "Public sector corruption, executive corruption, legislative corruption, "
        "judicial corruption, and bribery across branches of government.",
        [
            "v2x_corr",
            "v2x_execorr",
            "v2xlg_legcorr",
            "v2jucorrdc",
            "v2excrptps",
            "v2exbribe",
            "v2exembez",
            "v2exthftps",
        ],
    ),
    (
        "vdem_rule_of_law",
        "Rule of Law and Judicial Independence",
        "Judicial independence, compliance with judiciary and high court, "
        "access to justice, transparent law enforcement, and property rights.",
        [
            "v2xcl_rol",
            "v2x_jucon",
            "v2juhcind",
            "v2juncind",
            "v2juhccomp",
            "v2jucomp",
            "v2jureview",
            "v2jupurge",
            "v2jupack",
        ],
    ),
    (
        "vdem_elections",
        "Elections and Voting",
        "Election types, voter turnout, suffrage, electoral fraud and irregularities, "
        "election violence, election boycotts, vote buying, and campaign freedom.",
        [
            "v2x_suffr",
            "v2xel_frefair",
            "v2elvotbuy",
            "v2elirreg",
            "v2elintim",
            "v2elpeace",
            "v2elboycot",
            "v2elfrcamp",
            "v2elrgstry",
            "v2elmulpar",
            "v2elcomvot",
            "v2elsuffrage",
        ],
    ),
    (
        "vdem_civil_society",
        "Civil Society",
        "Civil society participation, CSO entry/exit, CSO repression, "
        "women's civil society participation, and civic engagement.",
        [
            "v2x_cspart",
            "v2csprtcpt",
            "v2cseeorgs",
            "v2csreprss",
            "v2cscnsult",
            "v2csgender",
            "v2csantimv",
            "v2csrlgcon",
        ],
    ),
    (
        "vdem_gender_equality",
        "Gender Equality and Women's Political Empowerment",
        "Women's political empowerment, women's civil liberties, women's civil "
        "society participation, female suffrage, and gender quota indicators.",
        [
            "v2x_gender",
            "v2x_gencl",
            "v2x_gencs",
            "v2x_genpp",
            "v2fsuffrage",
            "v2lgfemleg",
            "v2clgencl",
        ],
    ),
    (
        "vdem_media_freedom",
        "Media Freedom and Censorship",
        "Media bias, government censorship of media (internet and print), "
        "media self-censorship, journalist harassment, and media access.",
        [
            "v2meaccess",
            "v2mebias",
            "v2mecenefm",
            "v2mecrit",
            "v2meharjrn",
            "v2meslfcen",
            "v2mecenefi",
            "v2smgovfilprc",
            "v2smgovsmalt",
        ],
    ),
    (
        "vdem_executive_constraints",
        "Executive Constraints and Accountability",
        "Executive oversight, legislature investigates executive, judicial constraints "
        "on executive, executive respects constitution, and horizontal accountability.",
        [
            "v2x_execorr",
            "v2x_jucon",
            "v2xlg_legcon",
            "v2exrescon",
            "v2lginvstp",
            "v2lgotovst",
            "v2exhoshog",
            "v2expathhg",
            "v2expathhs",
        ],
    ),
    (
        "vdem_all_indices",
        "All V-Dem Democracy Indices (Overview)",
        "All five high-level democracy indices: Electoral, Liberal, Participatory, "
        "Deliberative, and Egalitarian democracy indices for cross-national comparison.",
        [
            "v2x_polyarchy",
            "v2x_libdem",
            "v2x_partipdem",
            "v2x_delibdem",
            "v2x_egaldem",
            "v2x_corr",
            "v2x_rule",
            "v2x_gender",
            "v2x_cspart",
        ],
    ),
]


class VDemSource:
    source_name: str = "vdem"

    # Cache available columns from the CSV header
    _available_cols: set[str] | None = None

    @classmethod
    def _get_available_cols(cls) -> set[str]:
        if cls._available_cols is not None:
            return cls._available_cols
        if not _CSV_FILE.exists():
            cls._available_cols = set()
            return cls._available_cols
        with open(_CSV_FILE, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, [])
        cls._available_cols = {c.strip('"').strip() for c in header}
        return cls._available_cols

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search curated V-Dem indicator groups by keyword."""
        if not _CSV_FILE.exists():
            logger.debug("V-Dem CSV not found at %s, skipping", _CSV_FILE)
            return []

        keywords = _extract_keywords(query)
        if not keywords:
            return []

        scored: list[tuple[int, tuple[str, str, str, list[str]]]] = []
        for group in _INDICATOR_GROUPS:
            ds_id, title, desc, _cols = group
            text = f"{title} {desc}".lower()
            hits = sum(1 for kw in keywords if kw in text)
            if hits > 0:
                scored.append((hits, group))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[DatasetResult] = []
        for _hits, (ds_id, title, desc, cols) in scored[:limit]:
            results.append(
                DatasetResult(
                    source=self.source_name,
                    id=ds_id,
                    title=f"V-Dem: {title}",
                    description=desc,
                    formats=["CSV"],
                    download_url=f"vdem://local/{ds_id}",
                    metadata={
                        "indicators": len(cols),
                        "citation": CITATION,
                        "version": "v15",
                        "license": "CC-BY-SA",
                    },
                )
            )

        return results

    async def get_download_url(self, dataset_id: str) -> str | None:
        return f"vdem://local/{dataset_id}" if dataset_id else None

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Extract relevant columns from the V-Dem CSV into a subset file."""
        if not _CSV_FILE.exists():
            logger.warning("V-Dem CSV not found at %s", _CSV_FILE)
            return None

        # Find the matching indicator group
        group = None
        for g in _INDICATOR_GROUPS:
            if g[0] == dataset_id:
                group = g
                break

        if group is None:
            logger.warning("Unknown V-Dem dataset_id: %s", dataset_id)
            return None

        _ds_id, _title, _desc, indicator_cols = group

        # Filter to columns that actually exist in the CSV
        available = self._get_available_cols()
        selected_cols = _ID_COLS + [c for c in indicator_cols if c in available]

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{dataset_id}.csv"

        try:
            with open(_CSV_FILE, newline="", encoding="utf-8") as infile:
                reader = csv.DictReader(infile)
                if reader.fieldnames is None:
                    return None

                # Only keep columns we need
                out_cols = [c for c in selected_cols if c in reader.fieldnames]

                with open(dest, "w", newline="", encoding="utf-8") as outfile:
                    writer = csv.DictWriter(outfile, fieldnames=out_cols)
                    writer.writeheader()
                    for row in reader:
                        writer.writerow({c: row[c] for c in out_cols})

            logger.info("V-Dem extract: %s -> %d columns", dataset_id, len(out_cols))
            return dest
        except (OSError, KeyError) as exc:
            logger.warning("V-Dem extraction failed for %s: %s", dataset_id, exc)
            return None
