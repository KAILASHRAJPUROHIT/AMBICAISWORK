# Security review: Voucher Format Router

## Purpose

Aradhana Ornate AutoPrint routes Ornate voucher copies on PC2:

- The approved office Sales Voucher first copy prints to `HP LaserJet P1007`.
- The second Sales Voucher copy, all Purchase/URD vouchers, extra copies, and uncertain states print to the P355 route.

## Release artifact

- File: `AradhanaOrnateAutoPrint.exe`
- SHA-256: `8898BCA405D34604C158965F9BE8E82A8A3E413A3955C6D2336971AA991372DC`
- Companion visual reference: `office-sales-voucher-format-reference.png`
- Reference SHA-256: `C059CBCF923E5331FE589364783B9365BA33CC43AD3C70D6BF7E3140D00C729F`

## Local-only behavior

The application observes only windows owned by `D:\Ornnx\ONX.exe`.
It captures the local `Voucher Print` window with Windows `PrintWindow`; no desktop recording, uploads, browser access, or cloud OCR is used.
The capture is compared in memory with the approved office-format reference and is not retained by the router.

The format must match `GST Sales Voucher (A4) Shree Aradhana` and follow a real foreground `Alt+P` event before P1007 can be selected. A mismatch, failed capture, absent reference, or missing Alt+P uses P355.

## Required approval

Endpoint security should approve the artifact through the organisation's normal signed-release or hash-review process. Do not weaken scanning globally or create broad exclusions.

