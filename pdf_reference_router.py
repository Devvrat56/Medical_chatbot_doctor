import os
import re
from typing import List, Dict


class PDFReferenceRouter:
    """
    Routes user questions to relevant PDF references.
    Designed for medical / academic use.
    """

    def __init__(self, pdf_folder: str = "pdfs"):
        self.pdf_folder = pdf_folder
        self.pdf_index = self._index_pdfs()

    def _index_pdfs(self) -> Dict[str, str]:
        """
        Create a searchable index of PDFs.
        """
        index = {}
        for file in os.listdir(self.pdf_folder):
            if file.lower().endswith(".pdf"):
                key = file.lower().replace("_", " ").replace(".pdf", "")
                index[key] = file
        return index

    def _normalize(self, text: str) -> str:
        return re.sub(r"[^a-z0-9 ]", "", text.lower())

    def find_relevant_pdfs(self, user_query: str) -> List[str]:
        """
        Match user query with PDF names using keyword overlap.
        """
        query = self._normalize(user_query)
        results = []

        for key, pdf_file in self.pdf_index.items():
            key_words = set(key.split())
            query_words = set(query.split())

            # simple intersection logic
            score = len(key_words & query_words)

            if score > 0:
                results.append(pdf_file)

        return results

    def build_streamlit_links(self, pdf_list: List[str]) -> List[str]:
        """
        Return clickable Streamlit markdown links.
        """
        links = []
        for pdf in pdf_list:
            links.append(
                f"- 📄 **{pdf}** → [Open PDF](pdfs/{pdf})"
            )
        return links
