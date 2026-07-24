from pathlib import Path

import fitz


def generate_sample_pdf(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "GroundedPDF Evaluation Brief\n\n"
        "This synthetic report is released under the MIT license with the GroundedPDF project.\n\n"
        "The pilot evaluated a local-first document research workflow while keeping files on the user's machine.",
        fontsize=11,
    )
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "Pilot Findings\n\n"
        "The measured efficiency gain was 37 percent during the six-week pilot.\n\n"
        "Reviewers attributed the improvement to direct page citations and faster source verification.",
        fontsize=11,
    )
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "Limitations\n\n"
        "The pilot used synthetic documents and a small reviewer group. Results should not be generalized without further study.",
        fontsize=11,
    )
    document.set_metadata(
        {
            "title": "GroundedPDF Evaluation Brief",
            "author": "GroundedPDF contributors",
            "subject": "Synthetic sample document for deterministic testing",
        }
    )
    # A new PDF trailer ID normally includes time-dependent data. Omitting it
    # keeps the documented fixture byte-for-byte reproducible across runs.
    document.save(output, no_new_id=True)
    document.close()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / "sample_documents" / "groundedpdf-sample.pdf"
    generate_sample_pdf(output)
    print(f"Generated {output}")


if __name__ == "__main__":
    main()
