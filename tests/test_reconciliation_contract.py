from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_uses_only_real_reconciliation_endpoint():
    frontend_files = [
        ROOT / "frontend" / "src" / "api" / "client.ts",
        ROOT / "frontend" / "src" / "pages" / "ReconciliationQueuePage.tsx",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in frontend_files)

    assert "/api/reconciliation/open" in combined
    assert "/api/reviews/open" not in combined
    assert "/reviews/open" not in combined
    assert "`open`" not in combined
    assert "'open'" not in combined
    assert '"open"' not in combined


def test_frontend_rejects_mock_reconciliation_contract_values():
    page = (ROOT / "frontend" / "src" / "pages" / "ReconciliationQueuePage.tsx").read_text(encoding="utf-8")

    for value in ["---", "Review Item", "REVIEW", "mock_review_1", "pay_001", "bill_002"]:
        assert value in page
    assert "Reconciliation contract rejected" in page
    assert "data.map(normalizeReview)" in page


def test_frontend_reconciliation_timeout_and_retry_contract():
    client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    page = (ROOT / "frontend" / "src" / "pages" / "ReconciliationQueuePage.tsx").read_text(encoding="utf-8")

    assert "AbortController" in client
    assert "RECONCILIATION_TIMEOUT_MS = 15000" in client
    assert "Reconciliation request timed out. Please retry." in client
    assert "getOpenReviewsWithTimeout" in page
    assert "finally(() => setLoading(false))" in page
    assert "Retry" in page
    assert "active filters" in page


def test_frontend_payment_proof_opens_in_page_modal_not_new_tab():
    client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    page = (ROOT / "frontend" / "src" / "pages" / "ReconciliationQueuePage.tsx").read_text(encoding="utf-8")

    proof_helper = client.split("export async function fetchProofPreview", 1)[1].split("export async function getOpenEscalations", 1)[0]
    assert "window.open" not in proof_helper
    assert "return response.text()" in proof_helper
    assert "proofModal" in page
    assert "handleCopyProof" in page
    assert "fetchProofPreview" in page
