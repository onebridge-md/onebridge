"""AssetPipeline processes and downloads embedded images and attachments from OneNote HTML."""

import base64
import mimetypes
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

from onebridge.core.filesystem_writer import FileSystemWriter
from onebridge.core.graph_client import GraphAPIError, OneNoteGraphClient
from onebridge.utils.filesystem import sanitize_filename


class AssetPipeline:
    """Discovers, downloads, and persists images and file attachments for a page."""

    def __init__(
        self,
        graph_client: Optional[OneNoteGraphClient] = None,
        fs_writer: Optional[FileSystemWriter] = None,
    ):
        self.graph_client = graph_client or OneNoteGraphClient()
        self.fs_writer = fs_writer or FileSystemWriter()

    def _guess_image_extension(self, content_type: Optional[str], data_bytes: Optional[bytes] = None) -> str:
        """Guesses appropriate image extension from content type or magic numbers."""
        if content_type:
            ext = mimetypes.guess_extension(content_type)
            if ext:
                if ext == ".jpe":
                    return ".jpg"
                return ext

        if data_bytes:
            if data_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                return ".png"
            elif data_bytes.startswith(b"\xff\xd8\xff"):
                return ".jpg"
            elif data_bytes.startswith(b"GIF87a") or data_bytes.startswith(b"GIF89a"):
                return ".gif"
            elif data_bytes.startswith(b"RIFF") and b"WEBP" in data_bytes[:12]:
                return ".webp"
            elif data_bytes.startswith(b"%PDF"):
                return ".pdf"

        return ".png"

    def process_assets(
        self,
        html_content: str,
        section_dir: Path,
        token: str,
        page_title: str = "",
    ) -> Tuple[Dict[str, str], Dict[str, str], List[str], List[str]]:
        """Scans page HTML for images and attachments, downloads them, and returns replacement maps.
        
        Args:
            html_content: Raw page XHTML/HTML from Microsoft Graph.
            section_dir: Section directory where IMAGENS/ and ANEXOS/ will reside.
            token: Valid Graph API access token.
            page_title: Title of page (for fallback asset naming).
            
        Returns:
            Tuple of:
            - image_map: {original_src: "IMAGENS/filename.png"}
            - attachment_map: {original_data_or_key: "ANEXOS/filename.pdf"}
            - downloaded_images: list of image filenames saved
            - downloaded_attachments: list of attachment filenames saved
        """
        soup = BeautifulSoup(html_content, "html.parser")
        images_dir = self.fs_writer.get_images_dir(section_dir)
        attachments_dir = self.fs_writer.get_attachments_dir(section_dir)

        image_map: Dict[str, str] = {}
        attachment_map: Dict[str, str] = {}
        downloaded_images: List[str] = []
        downloaded_attachments: List[str] = []

        # 1. Process <img> tags
        img_tags = soup.find_all("img")
        for idx, img in enumerate(img_tags, start=1):
            src = img.get("src") or img.get("data-fullres-src")
            if not src:
                continue

            # Check if inline base64
            if src.startswith("data:image/"):
                match = re.match(r"data:(image\/[^;]+);base64,(.+)", src, re.DOTALL)
                if match:
                    mime = match.group(1)
                    raw_b64 = match.group(2)
                    try:
                        img_bytes = base64.b64decode(raw_b64)
                        ext = self._guess_image_extension(mime, img_bytes)
                        img_name = f"imagem_{idx:02d}{ext}"
                        _, saved_name = self.fs_writer.write_asset(images_dir, img_name, img_bytes)
                        rel_path = f"IMAGENS/{saved_name}"
                        image_map[src] = rel_path
                        downloaded_images.append(saved_name)
                        continue
                    except Exception:
                        pass

            # Download via Graph API
            try:
                img_bytes = self.graph_client.get_binary_resource(src, token=token)
                mime = img.get("data-src-type")
                ext = self._guess_image_extension(mime, img_bytes)
                
                alt = img.get("alt") or ""
                if alt and len(alt) <= 40 and not any(c in alt for c in "/\\:?*\"<>|"):
                    stem = sanitize_filename(alt)
                    img_name = f"{stem}{ext}"
                else:
                    img_name = f"imagem_{idx:02d}{ext}"

                _, saved_name = self.fs_writer.write_asset(images_dir, img_name, img_bytes)
                rel_path = f"IMAGENS/{saved_name}"
                image_map[src] = rel_path
                downloaded_images.append(saved_name)
            except Exception as e:
                # Log or ignore image download failure without crashing entire export
                pass

        # 2. Process <object> attachment tags
        object_tags = soup.find_all("object")
        for idx, obj in enumerate(object_tags, start=1):
            data_url = obj.get("data")
            attachment_name = obj.get("data-attachment") or obj.get("data-filename")
            
            if not data_url and not attachment_name:
                continue

            if not attachment_name:
                attachment_name = f"anexo_{idx:02d}.bin"

            # Fallback if data is a valid Graph resource URL
            if data_url:
                try:
                    obj_bytes = self.graph_client.get_binary_resource(data_url, token=token)
                    _, saved_name = self.fs_writer.write_asset(attachments_dir, attachment_name, obj_bytes)
                    rel_path = f"ANEXOS/{saved_name}"
                    attachment_map[data_url] = rel_path
                    if attachment_name:
                        attachment_map[attachment_name] = rel_path
                    downloaded_attachments.append(saved_name)
                except Exception:
                    pass

        return image_map, attachment_map, downloaded_images, downloaded_attachments
