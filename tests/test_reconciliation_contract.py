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
