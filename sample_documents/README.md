# Sample document

Run `make sample` to generate `groundedpdf-sample.pdf`. The document is synthetic, contains no
personal or proprietary information, and is distributed under this repository's MIT license.

Deterministic verification question: **What efficiency gain was measured in the pilot?**

Expected evidence: **37 percent**, on page **2**. The PDF itself is generated rather than committed
so tests can reproduce it exactly with the installed PyMuPDF version.

`expected.json` is the machine-readable version of the same facts (question, expected answer, and
page) used by the automated sample-PDF tests.
