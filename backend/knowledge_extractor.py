"""
Knowledge Extractor for Vulcan OmniPro 220 Documentation

Extracts text, images, and structured information from PDF manuals.
"""

import json
import os
import base64
from pathlib import Path
from typing import Optional, Dict, List
import fitz  # PyMuPDF


def get_page_as_base64(pdf_path: str, page_num: int) -> Optional[Dict]:
    """Render a PDF page as a base64 encoded image."""
    try:
        doc = fitz.open(pdf_path)
        if page_num < 0 or page_num >= len(doc):
            return None

        page = doc[page_num]
        # Render at 2x resolution for clarity
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat)

        img_bytes = pix.tobytes("png")
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")

        doc.close()

        return {
            "base64": img_base64,
            "media_type": "image/png",
            "width": pix.width,
            "height": pix.height
        }
    except Exception as e:
        print(f"Error rendering page: {e}")
        return None


class KnowledgeExtractor:
    """Extract and index knowledge from PDF manuals."""

    def __init__(self, files_dir: str, output_dir: str):
        self.files_dir = Path(files_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def extract_all(self) -> Dict:
        """Extract knowledge from all PDF files."""
        knowledge_base = {
            "documents": [],
            "sections": [],
            "images": []
        }

        pdf_files = list(self.files_dir.glob("*.pdf"))

        for pdf_path in pdf_files:
            print(f"Processing {pdf_path.name}...")
            doc_info = self._extract_document(pdf_path)
            knowledge_base["documents"].append(doc_info)
            knowledge_base["sections"].extend(doc_info.get("sections", []))
            knowledge_base["images"].extend(doc_info.get("images", []))

        # Save the index
        index_path = self.output_dir / "knowledge_index.json"
        with open(index_path, "w") as f:
            json.dump(knowledge_base, f, indent=2)

        print(f"Extracted {len(knowledge_base['sections'])} sections and {len(knowledge_base['images'])} images")
        return knowledge_base

    def _extract_document(self, pdf_path: Path) -> Dict:
        """Extract information from a single PDF."""
        doc = fitz.open(pdf_path)

        doc_info = {
            "name": pdf_path.stem,
            "title": pdf_path.stem.replace("-", " ").title(),
            "pages": [],
            "sections": [],
            "images": []
        }

        current_section = None
        section_content = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()

            doc_info["pages"].append({
                "number": page_num + 1,
                "text": text[:500]  # Preview
            })

            # Extract sections based on text patterns
            lines = text.split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Detect section headers (all caps, or numbered sections)
                if self._is_section_header(line):
                    # Save previous section
                    if current_section and section_content:
                        doc_info["sections"].append({
                            "title": current_section,
                            "document": pdf_path.stem,
                            "content": "\n".join(section_content),
                            "keywords": self._extract_keywords(current_section, section_content)
                        })

                    current_section = line
                    section_content = []
                else:
                    section_content.append(line)

            # Extract images from page
            images = self._extract_page_images(page, page_num, pdf_path.stem)
            doc_info["images"].extend(images)

        # Save final section
        if current_section and section_content:
            doc_info["sections"].append({
                "title": current_section,
                "document": pdf_path.stem,
                "content": "\n".join(section_content),
                "keywords": self._extract_keywords(current_section, section_content)
            })

        doc.close()
        return doc_info

    def _is_section_header(self, line: str) -> bool:
        """Check if a line is likely a section header."""
        if len(line) < 3 or len(line) > 100:
            return False

        # All caps headers
        if line.isupper() and len(line) > 5:
            return True

        # Numbered sections
        if line[0].isdigit() and "." in line[:5]:
            return True

        # Common header patterns
        headers = ["WARNING", "CAUTION", "NOTE", "IMPORTANT", "SPECIFICATIONS",
                   "SETUP", "OPERATION", "MAINTENANCE", "TROUBLESHOOTING"]
        if any(h in line.upper() for h in headers):
            return True

        return False

    def _extract_keywords(self, title: str, content: List[str]) -> List[str]:
        """Extract relevant keywords from section content."""
        keywords = set()

        # Technical terms to look for
        terms = [
            "mig", "tig", "stick", "flux", "gmaw", "gtaw", "smaw", "fcaw",
            "voltage", "amperage", "wire", "gas", "polarity", "dcep", "dcen",
            "duty cycle", "weld", "torch", "ground", "clamp", "electrode",
            "argon", "co2", "steel", "aluminum", "stainless"
        ]

        full_text = (title + " " + " ".join(content)).lower()

        for term in terms:
            if term in full_text:
                keywords.add(term)

        return list(keywords)

    def _extract_page_images(self, page, page_num: int, doc_name: str) -> List[Dict]:
        """Extract images from a PDF page."""
        images = []

        try:
            image_list = page.get_images()

            for img_index, img in enumerate(image_list):
                xref = img[0]

                try:
                    base_image = page.parent.extract_image(xref)
                    image_bytes = base_image["image"]

                    # Save image
                    img_filename = f"{doc_name}_page{page_num + 1}_img{img_index + 1}.png"
                    img_path = self.output_dir / img_filename

                    with open(img_path, "wb") as f:
                        f.write(image_bytes)

                    images.append({
                        "filename": img_filename,
                        "page": page_num + 1,
                        "document": doc_name,
                        "context": page.get_text()[:200],
                        "base64": base64.b64encode(image_bytes).decode("utf-8"),
                        "media_type": f"image/{base_image.get('ext', 'png')}"
                    })
                except Exception as e:
                    print(f"Error extracting image: {e}")
                    continue

        except Exception as e:
            print(f"Error processing page images: {e}")

        return images


if __name__ == "__main__":
    # Test extraction
    extractor = KnowledgeExtractor(
        files_dir="../files",
        output_dir="../knowledge"
    )
    knowledge = extractor.extract_all()
    print(f"Extracted {len(knowledge['documents'])} documents")
