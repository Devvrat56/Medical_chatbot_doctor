import os

class PDFReferenceRouter:
    def __init__(self, pdf_folder="pdfs"):
        self.pdf_folder = pdf_folder

        # ✅ SAFETY CHECK
        if not os.path.exists(self.pdf_folder):
            os.makedirs(self.pdf_folder)

        self.pdf_index = self._index_pdfs()

    def _index_pdfs(self):
        index = []

        for file in os.listdir(self.pdf_folder):
            if file.lower().endswith(".pdf"):
                index.append(file)

        return index
