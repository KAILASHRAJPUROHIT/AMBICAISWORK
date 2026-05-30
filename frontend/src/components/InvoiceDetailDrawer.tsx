import React from 'react';
import type { ReconciliationItem } from '../mockReconciliationData';
import type { PrimeInvoiceDetail, PrimeProductDetail, PrimePaymentDetailEntry } from '../mockInvoiceDetails';
import { mockPrimeInvoiceDetails } from '../mockInvoiceDetails';
import '../Reconciliation.css'; // Import shared styles

interface InvoiceDetailDrawerProps {
  item: ReconciliationItem;
  onClose: () => void;
}

const InvoiceDetailDrawer: React.FC<InvoiceDetailDrawerProps> = ({ item, onClose }) => {
  // In a real application, you would fetch this detailed data based on item.id
  // For now, we find it from our mockPrimeInvoiceDetails
  const primeInvoiceDetail: PrimeInvoiceDetail | undefined = mockPrimeInvoiceDetails.find(
    (detail) => detail.id === item.id
  );

  if (!primeInvoiceDetail) {
    return (
      <div className="drawer-overlay" onClick={onClose}>
        <div className="drawer-content" onClick={(e) => e.stopPropagation()}>
          <div className="drawer-header">
            <h2>Invoice Details: {item.billNo}</h2>
            <button className="drawer-close-button" onClick={onClose}>
              &times;
            </button>
          </div>
          <div className="drawer-body">
            <div className="empty-state">No detailed invoice information available for this item.</div>
          </div>
        </div>
      </div>
    );
  }

  const formatCurrency = (amount: number) => {
    return `₹${amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  const getStatusClassName = (status: ReconciliationItem['status']) => {
    switch (status) {
      case 'Verified': return 'status-verified';
      case 'Pending': return 'status-pending';
      case 'Delivered Before Payment': return 'status-delivered-before-payment';
      case 'Risk / Mismatch': return 'status-risk-mismatch';
      case 'Cheque Pending': return 'status-cheque-pending';
      case 'Archived': return 'status-archived';
      default: return '';
    }
  };

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="drawer-content" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <h2>Invoice Details: {primeInvoiceDetail.invoiceNo}</h2>
          <button className="drawer-close-button" onClick={onClose}>
            &times;
          </button>
        </div>
        <div className="drawer-body">
          {/* 1. Invoice Details */}
          <section className="drawer-section">
            <h3>Invoice Details</h3>
            <div className="detail-item">
              <span className="detail-label">Voucher No:</span>
              <span className="detail-value">{primeInvoiceDetail.voucherNo}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Invoice No:</span>
              <span className="detail-value">{primeInvoiceDetail.invoiceNo}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Invoice Date:</span>
              <span className="detail-value">{primeInvoiceDetail.invoiceDate}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Bill Type:</span>
              <span className="detail-value">{primeInvoiceDetail.billType}</span>
            </div>
          </section>

          {/* 2. Customer Details */}
          <section className="drawer-section">
            <h3>Customer Details</h3>
            <div className="detail-item">
              <span className="detail-label">Customer Code:</span>
              <span className="detail-value">{primeInvoiceDetail.customerCode}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Customer Name:</span>
              <span className="detail-value">{primeInvoiceDetail.customerName}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Mobile:</span>
              <span className="detail-value">{primeInvoiceDetail.mobile}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Address:</span>
              <span className="detail-value">{primeInvoiceDetail.address}</span>
            </div>
          </section>

          {/* 3. Product Details */}
          <section className="drawer-section">
            <h3>Product Details</h3>
            {primeInvoiceDetail.productDetails.length > 0 ? (
              <div className="product-details-list">
                {primeInvoiceDetail.productDetails.map((product: PrimeProductDetail, index: number) => (
                  <div key={index} className="product-item">
                    <div className="detail-item">
                      <span className="detail-label">Product Name:</span>
                      <span className="detail-value">{product.productName}</span>
                    </div>
                    {product.grossWeight > 0 && (
                      <div className="detail-item">
                        <span className="detail-label">Gross Weight:</span>
                        <span className="detail-value">{product.grossWeight}</span>
                      </div>
                    )}
                    {product.netWeight > 0 && (
                      <div className="detail-item">
                        <span className="detail-label">Net Weight:</span>
                        <span className="detail-value">{product.netWeight}</span>
                      </div>
                    )}
                    <div className="detail-item">
                      <span className="detail-label">Rate:</span>
                      <span className="detail-value">{formatCurrency(product.rate)}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Amount:</span>
                      <span className="detail-value">{formatCurrency(product.amount)}</span>
                    </div>
                    {primeInvoiceDetail.productDetails.length > 1 && index < primeInvoiceDetail.productDetails.length - 1 && (
                      <hr style={{ borderTop: '1px dotted #eee', margin: '15px 0' }} />
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state-small">No product details available.</div>
            )}
          </section>

          {/* 4. GST Details */}
          <section className="drawer-section">
            <h3>GST Details</h3>
            <div className="detail-item">
              <span className="detail-label">Taxable Amount:</span>
              <span className="detail-value">{formatCurrency(primeInvoiceDetail.taxableAmount)}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">CGST:</span>
              <span className="detail-value">{formatCurrency(primeInvoiceDetail.cgst)}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">SGST:</span>
              <span className="detail-value">{formatCurrency(primeInvoiceDetail.sgst)}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">IGST:</span>
              <span className="detail-value">{formatCurrency(primeInvoiceDetail.igst)}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Invoice Total:</span>
              <span className="detail-value">{formatCurrency(primeInvoiceDetail.invoiceTotal)}</span>
            </div>
          </section>

          {/* 5. Payment Summary */}
          <section className="drawer-section">
            <h3>Payment Summary</h3>
            <div className="payment-details-grid">
              {primeInvoiceDetail.paymentSummary.advance > 0 && (
                <div className="detail-item">
                  <span className="detail-label">Advance:</span>
                  <span className="detail-value">{formatCurrency(primeInvoiceDetail.paymentSummary.advance)}</span>
                </div>
              )}
              {primeInvoiceDetail.paymentSummary.cash > 0 && (
                <div className="detail-item">
                  <span className="detail-label">Cash:</span>
                  <span className="detail-value">{formatCurrency(primeInvoiceDetail.paymentSummary.cash)}</span>
                </div>
              )}
              {primeInvoiceDetail.paymentSummary.bank > 0 && (
                <div className="detail-item">
                  <span className="detail-label">Bank:</span>
                  <span className="detail-value">{formatCurrency(primeInvoiceDetail.paymentSummary.bank)}</span>
                </div>
              )}
              {primeInvoiceDetail.paymentSummary.card > 0 && (
                <div className="detail-item">
                  <span className="detail-label">Card:</span>
                  <span className="detail-value">{formatCurrency(primeInvoiceDetail.paymentSummary.card)}</span>
                </div>
              )}
              {primeInvoiceDetail.paymentSummary.cheque > 0 && (
                <div className="detail-item">
                  <span className="detail-label">Cheque:</span>
                  <span className="detail-value">{formatCurrency(primeInvoiceDetail.paymentSummary.cheque)}</span>
                </div>
              )}
              {primeInvoiceDetail.paymentSummary.other > 0 && (
                <div className="detail-item">
                  <span className="detail-label">Other:</span>
                  <span className="detail-value">{formatCurrency(primeInvoiceDetail.paymentSummary.other)}</span>
                </div>
              )}
              {Object.values(primeInvoiceDetail.paymentSummary).every(amount => amount === 0) && (
                <div className="empty-state-small">No payment summary available.</div>
              )}
            </div>
          </section>

          {/* 6. Payment Detail Entries */}
          <section className="drawer-section">
            <h3>Payment Detail Entries</h3>
            {primeInvoiceDetail.paymentDetailEntries.length > 0 ? (
              <div className="table-container-small">
                <table className="reconciliation-table-small">
                  <thead>
                    <tr>
                      <th>Acc Code</th>
                      <th>Acc Name</th>
                      <th>Against Voucher</th>
                      <th>Cheque No</th>
                      <th>UTR Ref</th>
                      <th>Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {primeInvoiceDetail.paymentDetailEntries.map((entry: PrimePaymentDetailEntry, index: number) => (
                      <tr key={index}>
                        <td>{entry.accountCode}</td>
                        <td>{entry.accountName}</td>
                        <td>{entry.againstVoucher}</td>
                        <td>{entry.chequeNo || '-'}</td>
                        <td>{entry.utrReference || '-'}</td>
                        <td>{formatCurrency(entry.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty-state-small">No payment detail entries available.</div>
            )}
          </section>

          {/* 7. Audit Information */}
          <section className="drawer-section">
            <h3>Audit Information</h3>
            <div className="detail-item">
              <span className="detail-label">Extraction Source:</span>
              <span className="detail-value">{primeInvoiceDetail.extractionSource}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Extracted At:</span>
              <span className="detail-value">{new Date(primeInvoiceDetail.extractedAt).toLocaleString()}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Match Confidence:</span>
              <span className="detail-value">{primeInvoiceDetail.matchConfidence}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Status:</span>
              <span className={`status-badge ${getStatusClassName(primeInvoiceDetail.status)}`}>
                {primeInvoiceDetail.status}
              </span>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

export default InvoiceDetailDrawer;
