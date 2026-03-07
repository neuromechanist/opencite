"""Convert PMC BioC JSON to markdown."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Map BioC section_type to default markdown heading
_SECTION_HEADINGS: dict[str, str] = {
    "INTRO": "Introduction",
    "METHODS": "Methods",
    "RESULTS": "Results",
    "DISCUSS": "Discussion",
    "CONCL": "Conclusion",
    "ABSTRACT": "Abstract",
    "SUPPL": "Supplementary Material",
    "ACK_FUND": "Acknowledgments",
    "COMP_INT": "Competing Interests",
    "AUTH_CONT": "Author Contributions",
    "ABBR": "Abbreviations",
    "APPENDIX": "Appendix",
    "CASE": "Case Report",
    "REF": "References",
}


def bioc_to_markdown(
    document: dict,
    images_dir: str | None = None,
) -> str:
    """Convert a BioC document to markdown.

    Args:
        document: A BioC document dict (the element inside
            collection.documents[0]). Must have a "passages" list.
        images_dir: Relative path prefix for image references in markdown.
            If None, images are referenced by filename only.

    Returns:
        Markdown-formatted text.
    """
    passages = document.get("passages", [])
    if not passages:
        return ""

    parts: list[str] = []
    current_section: str = ""
    seen_section_titles: set[str] = set()

    for passage in passages:
        infons = passage.get("infons", {})
        section_type = infons.get("section_type", "")
        ptype = infons.get("type", "")
        text = passage.get("text", "").strip()

        if not text:
            continue

        # Title (article title)
        if ptype == "front" and section_type == "TITLE":
            parts.append(f"# {text}\n")
            continue

        # Section headings from the article structure
        if ptype in ("title", "title_1"):
            # Major section heading
            if section_type != current_section:
                current_section = section_type
            heading = text
            if heading not in seen_section_titles:
                seen_section_titles.add(heading)
                parts.append(f"## {heading}\n")
            continue

        if ptype == "title_2":
            parts.append(f"### {text}\n")
            continue

        if ptype == "title_3":
            parts.append(f"#### {text}\n")
            continue

        # Abstract: emit section heading if we haven't yet
        if section_type == "ABSTRACT" and ptype == "abstract":
            if "Abstract" not in seen_section_titles:
                seen_section_titles.add("Abstract")
                parts.append("## Abstract\n")
            parts.append(f"{text}\n")
            continue

        # For body sections, emit a default heading if no explicit title seen
        if (
            section_type in _SECTION_HEADINGS
            and section_type != current_section
            and ptype == "paragraph"
        ):
            heading = _SECTION_HEADINGS[section_type]
            if heading not in seen_section_titles:
                seen_section_titles.add(heading)
                parts.append(f"## {heading}\n")
            current_section = section_type

        # Figures
        if ptype in ("fig_caption", "fig_title_caption"):
            fig_file = infons.get("file", "")
            fig_id = infons.get("id", "")

            if fig_file and _is_image_file(fig_file):
                img_path = f"{images_dir}/{fig_file}" if images_dir else fig_file
                caption = text
                label = f"**Figure {fig_id}**: " if fig_id else ""
                parts.append(f"![{fig_id or 'figure'}]({img_path})\n")
                parts.append(f"{label}{caption}\n")
            else:
                label = f"**Figure {fig_id}**: " if fig_id else ""
                parts.append(f"{label}{text}\n")
            continue

        # Tables
        if ptype in ("table_caption", "table_title_caption"):
            table_id = infons.get("id", "")
            label = f"**Table {table_id}**: " if table_id else ""
            parts.append(f"{label}{text}\n")
            continue

        if ptype == "table":
            parts.append(_format_table_text(text))
            continue

        if ptype == "table_footnote":
            parts.append(f"*{text}*\n")
            continue

        # References
        if section_type == "REF" and ptype == "ref":
            if "References" not in seen_section_titles:
                seen_section_titles.add("References")
                parts.append("## References\n")
                current_section = "REF"
            parts.append(f"- {text}\n")
            continue

        # Footnotes
        if ptype == "footnote":
            parts.append(f"> {text}\n")
            continue

        # Regular paragraphs
        if ptype == "paragraph":
            parts.append(f"{text}\n")
            continue

        # Fallback: include unrecognized passage types as plain text
        if text and ptype not in ("front",):
            parts.append(f"{text}\n")

    return "\n".join(parts).strip() + "\n"


def extract_figure_files(document: dict) -> list[tuple[str, str]]:
    """Extract figure file references from a BioC document.

    Args:
        document: A BioC document dict.

    Returns:
        List of (figure_id, filename) tuples for image files.
    """
    figures: list[tuple[str, str]] = []
    seen: set[str] = set()

    for passage in document.get("passages", []):
        infons = passage.get("infons", {})
        fig_file = infons.get("file", "")
        fig_id = infons.get("id", "")

        if fig_file and _is_image_file(fig_file) and fig_file not in seen:
            seen.add(fig_file)
            figures.append((fig_id, fig_file))

    return figures


def extract_metadata(document: dict) -> dict:
    """Extract article metadata from the BioC front matter passage.

    Args:
        document: A BioC document dict.

    Returns:
        Dict with keys like doi, pmid, pmcid, year, license, authors, etc.
    """
    for passage in document.get("passages", []):
        infons = passage.get("infons", {})
        if infons.get("type") == "front":
            meta: dict = {}
            meta["doi"] = infons.get("article-id_doi", "")
            meta["pmcid"] = infons.get("article-id_pmc", "")
            meta["pmid"] = infons.get("article-id_pmid", "")
            meta["year"] = infons.get("year", "")
            meta["volume"] = infons.get("volume", "")
            meta["issue"] = infons.get("issue", "")
            meta["license"] = infons.get("license", "")
            meta["title"] = passage.get("text", "")

            # Extract authors from name_N keys
            authors = []
            for i in range(100):
                name_key = f"name_{i}"
                if name_key not in infons:
                    break
                authors.append(infons[name_key])
            meta["authors"] = authors

            return meta

    return {}


def _is_image_file(filename: str) -> bool:
    """Check if a filename is an image (not XML or other data)."""
    return bool(
        re.search(r"\.(jpg|jpeg|png|gif|svg|tiff|tif|bmp|webp)$", filename, re.I)
    )


def _format_table_text(text: str) -> str:
    """Format tab-separated table text as markdown table."""
    if not text.strip():
        return ""
    lines = text.strip().split("\n")

    rows: list[list[str]] = []
    for line in lines:
        # BioC tables use tab separation
        cells = line.split("\t")
        rows.append([c.strip() for c in cells])

    if not rows:
        return ""

    # Find max columns
    max_cols = max(len(r) for r in rows)
    # Pad rows to same width
    for row in rows:
        while len(row) < max_cols:
            row.append("")

    # Build markdown table
    parts: list[str] = []
    # Header row
    parts.append("| " + " | ".join(rows[0]) + " |")
    parts.append("| " + " | ".join("---" for _ in rows[0]) + " |")
    # Data rows
    for row in rows[1:]:
        parts.append("| " + " | ".join(row) + " |")

    return "\n".join(parts) + "\n"
