"""MarkdownConverter transforms OneNote XHTML/HTML into clean, standardized Markdown with frontmatter."""

import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from bs4 import BeautifulSoup, Tag
from markdownify import MarkdownConverter as BaseMarkdownConverter


class CustomMarkdownConverter(BaseMarkdownConverter):
    """Extended MarkdownConverter with support for OneNote specific tags and tables."""

    def convert_tr(self, el: Tag, text: str, *args, **kwargs) -> str:
        """Ensures proper Markdown table row formatting."""
        cells = el.find_all(["td", "th"])
        if not cells:
            return ""

        row_content = []
        for cell in cells:
            cell_text = cell.get_text(separator=" ", strip=True).replace("\n", " ")
            row_content.append(cell_text or " ")

        return "| " + " | ".join(row_content) + " |\n"

    def convert_table(self, el: Tag, text: str, *args, **kwargs) -> str:
        """Converts HTML table to standard GitHub Flavored Markdown table."""
        rows = el.find_all("tr")
        if not rows:
            return ""

        md_rows = []
        header_done = False

        for row in rows:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue

            cell_texts = [
                c.get_text(separator=" ", strip=True).replace("\n", " ") or " "
                for c in cells
            ]
            row_str = "| " + " | ".join(cell_texts) + " |"
            md_rows.append(row_str)

            if not header_done:
                delimiter = "| " + " | ".join(["---"] * len(cells)) + " |"
                md_rows.append(delimiter)
                header_done = True

        return "\n\n" + "\n".join(md_rows) + "\n\n"


class MarkdownConverter:
    """High-level converter handling OneNote DOM preprocessing, asset replacement, and YAML frontmatter."""

    def __init__(self):
        self._md_converter = CustomMarkdownConverter(
            heading_style="ATX",
            bullets="-",
            strip=["style", "script", "meta", "link"],
            autolinks=True,
        )

    def _build_frontmatter(self, metadata: Dict[str, Any]) -> str:
        """Constructs YAML frontmatter header from page metadata."""
        lines = ["---"]
        title = str(metadata.get("title", "Sem Título")).replace('"', '\\"')
        lines.append(f'title: "{title}"')

        if metadata.get("id"):
            lines.append(f'id: "{metadata["id"]}"')
        if metadata.get("notebook"):
            lines.append(f'notebook: "{metadata["notebook"]}"')
        if metadata.get("section_group"):
            lines.append(f'section_group: "{metadata["section_group"]}"')
        if metadata.get("section"):
            lines.append(f'section: "{metadata["section"]}"')
        if metadata.get("created_at"):
            lines.append(f'created_at: "{metadata["created_at"]}"')
        if metadata.get("modified_at"):
            lines.append(f'modified_at: "{metadata["modified_at"]}"')
        if metadata.get("web_url"):
            lines.append(f'original_url: "{metadata["web_url"]}"')

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines.append(f'exported_at: "{now_iso}"')
        lines.append("---\n")

        return "\n".join(lines)

    def _preprocess_html(
        self,
        soup: BeautifulSoup,
        image_map: Optional[Dict[str, str]] = None,
        attachment_map: Optional[Dict[str, str]] = None,
    ) -> None:
        """Transforms OneNote-specific tags in the BeautifulSoup tree before markdown conversion."""
        image_map = image_map or {}
        attachment_map = attachment_map or {}

        # 1. Transform <object data-attachment="..."> into clickable links
        for obj in soup.find_all("object"):
            data_url = obj.get("data")
            att_name = obj.get("data-attachment") or obj.get("data-filename") or "Anexo"
            local_target = attachment_map.get(data_url) or attachment_map.get(att_name)
            href = local_target if local_target else (data_url or "#")

            link_tag = soup.new_tag("a", href=href)
            link_tag.string = f"📎 {att_name}"
            obj.replace_with(link_tag)

        # 2. Transform <img> src into local IMAGENS/...
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-fullres-src")
            if src and src in image_map:
                img["src"] = image_map[src]

        # 3. Transform OneNote to-do tags into Markdown checkboxes
        for tag in soup.find_all(attrs={"data-tag": True}):
            tag_val = tag["data-tag"]
            if "to-do:completed" in tag_val:
                prefix = "- [x] "
            elif "to-do" in tag_val:
                prefix = "- [ ] "
            else:
                prefix = ""

            if prefix:
                # Prepend checkbox markdown
                if tag.string:
                    tag.string = f"{prefix}{tag.string}"
                else:
                    tag.insert(0, prefix)

    def convert(
        self,
        html_content: str,
        metadata: Optional[Dict[str, Any]] = None,
        image_map: Optional[Dict[str, str]] = None,
        attachment_map: Optional[Dict[str, str]] = None,
    ) -> str:
        """Converts raw OneNote HTML into full Markdown document with frontmatter.
        
        Args:
            html_content: Raw XHTML/HTML string from OneNote Graph API.
            metadata: Page metadata dictionary for YAML frontmatter.
            image_map: Map of original image URLs/sources to relative IMAGENS/ paths.
            attachment_map: Map of attachment URLs/names to relative ANEXOS/ paths.
            
        Returns:
            Standard Markdown string.
        """
        soup = BeautifulSoup(html_content, "html.parser")

        # Extract title from HTML if not in metadata
        if metadata is None:
            metadata = {}
        if not metadata.get("title"):
            title_tag = soup.find("title")
            if title_tag and title_tag.string:
                metadata["title"] = title_tag.string.strip()

        # Remove header/title tag from body if already part of frontmatter/page title
        title_elem = soup.find("title")
        if title_elem:
            title_elem.decompose()

        # Preprocess tags
        self._preprocess_html(soup, image_map=image_map, attachment_map=attachment_map)

        # Convert body to Markdown
        body = soup.find("body") or soup
        body_html = str(body)
        raw_markdown = self._md_converter.convert(body_html)

        # Clean up excessive newlines
        clean_markdown = re.sub(r"\n{3,}", "\n\n", raw_markdown).strip()

        # Build Frontmatter
        frontmatter = self._build_frontmatter(metadata)

        return f"{frontmatter}\n{clean_markdown}\n"
