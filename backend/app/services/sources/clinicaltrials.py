"""ClinicalTrials.gov API v2 adapter.

Uses the ClinicalTrials.gov REST API v2 at clinicaltrials.gov/api/v2
to search for and download clinical trial data. No authentication required.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.schemas.datasets import DatasetResult
from app.services.http_client import SourceHTTPClient

logger = logging.getLogger(__name__)

BASE_URL = "https://clinicaltrials.gov/api/v2"
_client = SourceHTTPClient("clinicaltrials", timeout=30.0)


class ClinicalTrialsSource:
    source_name: str = "clinicaltrials"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search ClinicalTrials.gov for studies matching *query*."""
        params = {
            "query.term": query,
            "pageSize": min(limit, 20),
            "format": "json",
            "fields": (
                "NCTId,BriefTitle,OverallStatus,Phase,"
                "EnrollmentCount,Condition,InterventionName,"
                "LeadSponsorName,StartDate,CompletionDate"
            ),
        }
        try:
            data = await _client.get_json(f"{BASE_URL}/studies", params=params)
        except Exception as exc:
            logger.warning("ClinicalTrials search failed for query=%r: %s", query, exc)
            return []

        results: list[DatasetResult] = []
        for study in data.get("studies", [])[:limit]:
            proto = study.get("protocolSection", {})
            ident = proto.get("identificationModule", {})
            status_mod = proto.get("statusModule", {})
            design = proto.get("designModule", {})
            sponsor_mod = proto.get("sponsorCollaboratorsModule", {})
            conditions_mod = proto.get("conditionsModule", {})

            nct_id = ident.get("nctId", "")
            if not nct_id:
                continue

            title = ident.get("briefTitle", "")
            status = status_mod.get("overallStatus", "")
            phases = design.get("phases", [])
            enrollment = design.get("enrollmentInfo", {}).get("count")
            sponsor = sponsor_mod.get("leadSponsor", {}).get("name", "")
            conditions = conditions_mod.get("conditions", [])

            desc_parts = []
            if status:
                desc_parts.append(f"Status: {status}")
            if phases:
                desc_parts.append(f"Phase: {', '.join(phases)}")
            if sponsor:
                desc_parts.append(f"Sponsor: {sponsor}")
            if conditions:
                desc_parts.append(f"Conditions: {', '.join(conditions[:3])}")

            results.append(
                DatasetResult(
                    source=self.source_name,
                    id=nct_id,
                    title=title,
                    description="; ".join(desc_parts)[:500],
                    formats=["JSON"],
                    download_url=f"{BASE_URL}/studies/{nct_id}?format=json",
                    metadata={
                        k: v
                        for k, v in {
                            "status": status,
                            "phase": ", ".join(phases) if phases else None,
                            "enrollment": enrollment,
                            "sponsor": sponsor,
                        }.items()
                        if v
                    },
                )
            )

        return results

    async def get_download_url(self, dataset_id: str) -> str | None:
        if not dataset_id:
            return None
        return f"{BASE_URL}/studies?query.term={dataset_id}&pageSize=100&format=json"

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download clinical trial data as JSON."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"clinicaltrials_{dataset_id}.json"

        params = {
            "query.term": dataset_id,
            "pageSize": 100,
            "format": "json",
        }
        try:
            data = await _client.get_json(f"{BASE_URL}/studies", params=params, use_cache=False)
            studies = data.get("studies", [])
            if not studies:
                logger.warning("ClinicalTrials returned no data for %s", dataset_id)
                return None

            # Flatten to tabular-friendly records
            records = []
            for study in studies:
                proto = study.get("protocolSection", {})
                ident = proto.get("identificationModule", {})
                status_mod = proto.get("statusModule", {})
                design = proto.get("designModule", {})
                sponsor_mod = proto.get("sponsorCollaboratorsModule", {})
                conditions_mod = proto.get("conditionsModule", {})

                records.append(
                    {
                        "nct_id": ident.get("nctId", ""),
                        "title": ident.get("briefTitle", ""),
                        "status": status_mod.get("overallStatus", ""),
                        "phase": ", ".join(design.get("phases", [])),
                        "enrollment": design.get("enrollmentInfo", {}).get("count"),
                        "sponsor": sponsor_mod.get("leadSponsor", {}).get("name", ""),
                        "conditions": ", ".join(conditions_mod.get("conditions", [])),
                        "start_date": status_mod.get("startDateStruct", {}).get("date"),
                        "completion_date": status_mod.get("completionDateStruct", {}).get("date"),
                    }
                )

            dest.write_text(json.dumps(records, ensure_ascii=False))
            return dest
        except Exception as exc:
            logger.warning("ClinicalTrials download failed for %s: %s", dataset_id, exc)
            return None
