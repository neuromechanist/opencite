"""PubMed E-utilities API client."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any

from opencite.clients.base import BaseClient
from opencite.models import Author, IDSet, Paper, Source

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class PubMedClient(BaseClient):
    """Client for the NCBI PubMed E-utilities API.

    Uses esearch for keyword queries, efetch for metadata retrieval,
    and elink for citation/reference traversal.
    """

    def __init__(self, config: Config):
        super().__init__(
            config=config,
            base_url=BASE_URL,
            rate_limit=config.pubmed_rate_limit,
            burst=3,
        )

    def _default_headers(self) -> dict[str, str]:
        return {}

    def _base_params(self) -> dict[str, str]:
        """Return params included in every request (API key, tool, email)."""
        params: dict[str, str] = {"tool": "opencite"}
        if self.config.pubmed_api_key:
            params["api_key"] = self.config.pubmed_api_key
        if self.config.contact_email:
            params["email"] = self.config.contact_email
        return params

    async def search(
        self,
        query: str,
        max_results: int = 20,
    ) -> list[Paper]:
        """Search PubMed using esearch + efetch."""
        # Step 1: esearch for PMIDs
        search_params: dict[str, Any] = {
            **self._base_params(),
            "db": "pubmed",
            "term": query,
            "retmax": min(max_results, 10000),
            "retmode": "json",
            "sort": "relevance",
        }
        resp = await self.get("/esearch.fcgi", params=search_params)
        data = resp.json()
        id_list = data.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return []

        return await self.fetch_by_pmids(id_list)

    async def fetch_by_pmids(self, pmids: list[str]) -> list[Paper]:
        """Fetch full paper metadata for a list of PMIDs via efetch."""
        papers: list[Paper] = []
        # Process in chunks of 200 (PubMed recommendation)
        for i in range(0, len(pmids), 200):
            chunk = pmids[i : i + 200]
            fetch_params: dict[str, Any] = {
                **self._base_params(),
                "db": "pubmed",
                "id": ",".join(chunk),
                "retmode": "xml",
            }
            try:
                resp = await self.get("/efetch.fcgi", params=fetch_params)
                chunk_papers = _parse_pubmed_xml(resp.text)
                papers.extend(chunk_papers)
            except Exception:
                logger.warning("PubMed efetch failed for chunk at %d", i)
        return papers

    async def lookup_pmid(self, pmid: str) -> Paper | None:
        """Look up a single paper by PMID."""
        results = await self.fetch_by_pmids([pmid])
        return results[0] if results else None

    async def lookup_doi(self, doi: str) -> Paper | None:
        """Look up a paper by DOI via PubMed search."""
        search_params: dict[str, Any] = {
            **self._base_params(),
            "db": "pubmed",
            "term": f"{doi}[lid]",
            "retmax": 1,
            "retmode": "json",
        }
        try:
            resp = await self.get("/esearch.fcgi", params=search_params)
            data = resp.json()
            id_list = data.get("esearchresult", {}).get("idlist", [])
            if not id_list:
                return None
            results = await self.fetch_by_pmids(id_list[:1])
            return results[0] if results else None
        except Exception:
            logger.debug("PubMed DOI lookup failed for %s", doi)
            return None

    async def citing_papers(
        self,
        pmid: str,
        max_results: int = 50,
    ) -> list[Paper]:
        """Find papers citing the given PMID using elink."""
        link_params: dict[str, Any] = {
            **self._base_params(),
            "dbfrom": "pubmed",
            "db": "pubmed",
            "id": pmid,
            "linkname": "pubmed_pubmed_citedin",
            "retmode": "json",
        }
        try:
            resp = await self.get("/elink.fcgi", params=link_params)
            data = resp.json()
            linked_ids = _extract_link_ids(data)
            if not linked_ids:
                return []
            return await self.fetch_by_pmids(linked_ids[:max_results])
        except Exception:
            logger.debug("PubMed citing papers lookup failed for %s", pmid)
            return []

    async def references(
        self,
        pmid: str,
        max_results: int = 50,
    ) -> list[Paper]:
        """Find papers referenced by the given PMID using elink."""
        link_params: dict[str, Any] = {
            **self._base_params(),
            "dbfrom": "pubmed",
            "db": "pubmed",
            "id": pmid,
            "linkname": "pubmed_pubmed_refs",
            "retmode": "json",
        }
        try:
            resp = await self.get("/elink.fcgi", params=link_params)
            data = resp.json()
            linked_ids = _extract_link_ids(data)
            if not linked_ids:
                return []
            return await self.fetch_by_pmids(linked_ids[:max_results])
        except Exception:
            logger.debug("PubMed references lookup failed for %s", pmid)
            return []


def _extract_link_ids(data: dict) -> list[str]:
    """Extract linked PMIDs from elink JSON response."""
    ids: list[str] = []
    for linkset in data.get("linksets", []):
        for linksetdb in linkset.get("linksetdbs", []):
            for link in linksetdb.get("links", []):
                ids.append(str(link))
    return ids


def _parse_pubmed_xml(xml_text: str) -> list[Paper]:
    """Parse PubMed efetch XML into Paper models."""
    papers: list[Paper] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("Failed to parse PubMed XML response")
        return []

    for article in root.findall(".//PubmedArticle"):
        paper = _parse_article(article)
        if paper:
            papers.append(paper)
    return papers


def _parse_article(article: ET.Element) -> Paper | None:
    """Parse a single PubmedArticle element into a Paper."""
    pmid_elem = article.find(".//PMID")
    title_elem = article.find(".//ArticleTitle")
    if pmid_elem is None or title_elem is None:
        return None

    pmid = pmid_elem.text or ""
    title = _get_element_text(title_elem)
    if not title:
        return None

    # DOI and PMCID from ArticleIdList
    doi = ""
    pmcid = ""
    for id_elem in article.findall(".//ArticleId"):
        id_type = id_elem.get("IdType", "")
        text = id_elem.text or ""
        if id_type == "doi" and not doi:
            doi = text
        elif id_type == "pmc" and not pmcid:
            pmcid = text

    ids = IDSet(doi=doi, pmid=pmid, pmcid=pmcid)

    # Year
    year = _extract_year(article)

    # Publication date string
    pub_date = _extract_pub_date(article)

    # Authors
    authors = _extract_authors(article)

    # Abstract
    abstract_parts = []
    for abs_elem in article.findall(".//AbstractText"):
        label = abs_elem.get("Label", "")
        text = _get_element_text(abs_elem)
        if text:
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
    abstract = " ".join(abstract_parts)
    if len(abstract) > 1000:
        abstract = abstract[:1000]

    # Journal
    source_venue = None
    journal_elem = article.find(".//Journal/Title")
    journal_name = (journal_elem.text or "") if journal_elem is not None else ""
    if journal_name:
        issn_elem = article.find(".//Journal/ISSN")
        issn = (issn_elem.text or "") if issn_elem is not None else ""
        source_venue = Source(name=journal_name, issn=issn)

    # MeSH terms
    mesh_terms = []
    for mesh_elem in article.findall(".//MeshHeading/DescriptorName"):
        name = mesh_elem.text or ""
        if name:
            mesh_terms.append(name)

    # Keywords
    topics = []
    for kw_elem in article.findall(".//Keyword"):
        kw = kw_elem.text or ""
        if kw:
            topics.append(kw)

    # Publication types
    pub_types = []
    for pt_elem in article.findall(".//PublicationType"):
        pt = pt_elem.text or ""
        if pt:
            pub_types.append(pt)
    pub_type = pub_types[0] if pub_types else ""

    # Grants
    grants = []
    for grant_elem in article.findall(".//Grant"):
        grant: dict[str, str] = {}
        grant_id_elem = grant_elem.find("GrantID")
        agency_elem = grant_elem.find("Agency")
        if grant_id_elem is not None and grant_id_elem.text:
            grant["award_id"] = grant_id_elem.text
        if agency_elem is not None and agency_elem.text:
            grant["funder"] = agency_elem.text
        if grant:
            grants.append(grant)

    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

    return Paper(
        title=title,
        ids=ids,
        authors=authors,
        year=year,
        source_venue=source_venue,
        publication_date=pub_date,
        pub_type=pub_type,
        abstract=abstract,
        topics=topics,
        mesh_terms=mesh_terms,
        url=url,
        data_sources={"pubmed"},
        grants=grants,
    )


def _get_element_text(elem: ET.Element) -> str:
    """Get all text content from an element, including mixed content with child tags."""
    parts = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        if child.text:
            parts.append(child.text)
        if child.tail:
            parts.append(child.tail)
    return "".join(parts).strip()


def _extract_year(article: ET.Element) -> int | None:
    """Extract publication year from PubDate."""
    year_elem = article.find(".//PubDate/Year")
    if year_elem is not None and year_elem.text and year_elem.text.isdigit():
        return int(year_elem.text)
    # Fallback: MedlineDate format like "2020 Jan-Feb"
    medline_date = article.find(".//PubDate/MedlineDate")
    if medline_date is not None and medline_date.text:
        match = re.search(r"(\d{4})", medline_date.text)
        if match:
            return int(match.group(1))
    return None


def _extract_pub_date(article: ET.Element) -> str:
    """Extract publication date as ISO string if possible."""
    year_elem = article.find(".//PubDate/Year")
    if year_elem is None or not year_elem.text:
        return ""
    year = year_elem.text
    month_elem = article.find(".//PubDate/Month")
    day_elem = article.find(".//PubDate/Day")
    month = (month_elem.text or "") if month_elem is not None else ""
    day = (day_elem.text or "") if day_elem is not None else ""
    # Convert month name to number if needed
    month_num = _month_to_num(month)
    if month_num and day:
        return f"{year}-{month_num:02d}-{int(day):02d}"
    if month_num:
        return f"{year}-{month_num:02d}"
    return year


_MONTH_MAP = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _month_to_num(month: str) -> int | None:
    """Convert month string to number. Handles 'Jan', '01', etc."""
    if not month:
        return None
    if month.isdigit():
        n = int(month)
        return n if 1 <= n <= 12 else None
    return _MONTH_MAP.get(month[:3].lower())


def _extract_authors(article: ET.Element) -> list[Author]:
    """Extract authors from PubMed XML."""
    authors = []
    for author_elem in article.findall(".//Author"):
        last_elem = author_elem.find("LastName")
        fore_elem = author_elem.find("ForeName")
        if last_elem is None or not last_elem.text:
            # Collective author or incomplete
            collective = author_elem.find("CollectiveName")
            if collective is not None and collective.text:
                authors.append(
                    Author(
                        name=collective.text,
                        family_name=collective.text,
                    )
                )
            continue
        family = last_elem.text
        given = (fore_elem.text or "") if fore_elem is not None else ""
        name = f"{given} {family}".strip() if given else family

        # ORCID from Identifier
        orcid = ""
        for ident in author_elem.findall("Identifier"):
            if ident.get("Source") == "ORCID" and ident.text:
                orcid = ident.text.replace("http://orcid.org/", "").replace(
                    "https://orcid.org/", ""
                )
                break

        authors.append(
            Author(
                name=name,
                family_name=family,
                given_name=given,
                orcid=orcid,
            )
        )
    return authors[:50]
