// frontend/src/mockInvoiceDetails.ts

export interface PrimeProductDetail {
  productName: string;
  grossWeight: number; // in grams or karats, depending on context for jewelry
  netWeight: number; // in grams or karats
  rate: number; // rate per unit of weight/item
  amount: number; // total amount for this product
}

export interface PrimePaymentDetailEntry {
  accountCode: string;
  accountName: string;
  againstVoucher: string;
  chequeNo: string | null;
  utrReference: string | null;
  amount: number;
}

export interface PrimeInvoiceDetail {
  id: string; // Corresponds to ReconciliationItem.id
  // 1. Invoice Details
  voucherNo: string;
  invoiceNo: string;
  invoiceDate: string; // YYYY-MM-DD
  billType: string;

  // 2. Customer Details
  customerCode: string;
  customerName: string;
  mobile: string;
  address: string;

  // 3. Product Details (list of products)
  productDetails: PrimeProductDetail[];

  // 4. GST Details
  taxableAmount: number;
  cgst: number;
  sgst: number;
  igst: number;
  invoiceTotal: number;

  // 5. Payment Summary
  paymentSummary: {
    advance: number;
    cash: number;
    bank: number;
    card: number;
    cheque: number;
    other: number;
  };

  // 6. Payment Detail Entries (Table data)
  paymentDetailEntries: PrimePaymentDetailEntry[];

  // 7. Audit Information
  extractionSource: string;
  extractedAt: string; // Timestamp
  matchConfidence: string;
  status: 'Verified' | 'Pending' | 'Delivered Before Payment' | 'Risk / Mismatch' | 'Cheque Pending' | 'Archived';
}

export const mockPrimeInvoiceDetails: PrimeInvoiceDetail[] = [
  {
    id: 'rec-001',
    voucherNo: 'VOU-2023-001',
    invoiceNo: 'INV-2023-001',
    invoiceDate: '2023-01-15',
    billType: 'Sales Invoice',
    customerCode: 'CUST-001',
    customerName: 'Alpha Corp',
    mobile: '9876543210',
    address: '123 Gold St, Jeweller Town, Mumbai, 400001',
    productDetails: [
      { productName: 'Gold Ring 22K', grossWeight: 5.5, netWeight: 5.0, rate: 6000, amount: 30000 },
      { productName: 'Diamond Pendant', grossWeight: 2.0, netWeight: 1.5, rate: 15000, amount: 22500 },
    ],
    taxableAmount: 52500,
    cgst: 2625,
    sgst: 2625,
    igst: 0,
    invoiceTotal: 57750,
    paymentSummary: { advance: 0, cash: 0, bank: 57750, card: 0, cheque: 0, other: 0 },
    paymentDetailEntries: [
      {
        accountCode: 'ACC-BNK-001',
        accountName: 'HDFC Bank',
        againstVoucher: 'PV-001',
        chequeNo: null,
        utrReference: 'UTR1234567890',
        amount: 57750,
      },
    ],
    extractionSource: 'Prime ERP',
    extractedAt: '2023-01-15T10:00:00Z',
    matchConfidence: 'High',
    status: 'Verified',
  },
  {
    id: 'rec-002',
    voucherNo: 'VOU-2023-002',
    invoiceNo: 'INV-2023-002',
    invoiceDate: '2023-01-16',
    billType: 'Sales Invoice',
    customerCode: 'CUST-002',
    customerName: 'Beta Ltd',
    mobile: '9988776655',
    address: '456 Silver Ln, Gemstone City, Delhi, 110001',
    productDetails: [
      { productName: 'Silver Bracelet', grossWeight: 20.0, netWeight: 18.0, rate: 80, amount: 1440 },
      { productName: 'Pearl Necklace', grossWeight: 10.0, netWeight: 10.0, rate: 500, amount: 5000 },
    ],
    taxableAmount: 6440,
    cgst: 322,
    sgst: 322,
    igst: 0,
    invoiceTotal: 7084,
    paymentSummary: { advance: 0, cash: 0, bank: 7084, card: 0, cheque: 0, other: 0 },
    paymentDetailEntries: [
      {
        accountCode: 'ACC-BNK-002',
        accountName: 'ICICI Bank',
        againstVoucher: 'PV-002',
        chequeNo: null,
        utrReference: 'UTR0987654321',
        amount: 7084,
      },
    ],
    extractionSource: 'Bank Statement',
    extractedAt: '2023-01-16T11:30:00Z',
    matchConfidence: 'Medium',
    status: 'Risk / Mismatch',
  },
  {
    id: 'rec-003',
    voucherNo: 'VOU-2023-003',
    invoiceNo: 'INV-2023-003',
    invoiceDate: '2023-01-17',
    billType: 'Repair Service',
    customerCode: 'CUST-003',
    customerName: 'Gamma Inc',
    mobile: '9765432109',
    address: '789 Bronze Rd, Jewel District, Kolkata, 700001',
    productDetails: [
      { productName: 'Watch Repair', grossWeight: 0, netWeight: 0, rate: 5000, amount: 5000 },
    ],
    taxableAmount: 5000,
    cgst: 250,
    sgst: 250,
    igst: 0,
    invoiceTotal: 5500,
    paymentSummary: { advance: 0, cash: 0, bank: 0, card: 0, cheque: 0, other: 0 },
    paymentDetailEntries: [],
    extractionSource: 'Email',
    extractedAt: '2023-01-17T09:00:00Z',
    matchConfidence: 'Low',
    status: 'Pending',
  },
];
