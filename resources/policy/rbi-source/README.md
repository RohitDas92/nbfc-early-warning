# RBI source documents

## Read this first — the framework was restructured

On **28 November 2025** the RBI withdrew roughly **9,445 circulars** and
re-issued the regulatory framework as Master Directions, one set per entity
type. A second tranche of **supervisory** directions followed on **31 July
2026**.

Every circular this project originally cited is therefore **withdrawn**. The
paragraph numbers moved as well, so a citation cannot be fixed by swapping the
document name — each provision has to be located again in the new text.

Verified so far:

- The NBFC IRACP Directions now point *elsewhere* for upgradation: paragraph 22
  says an asset shall not be upgraded merely by rescheduling, "unless it
  satisfies the conditions required for the upgradation as laid out in the
  Reserve Bank of India (Non-Banking Financial Companies – Resolution of
  Stressed Assets) Directions, 2025." **The upgrade rule moved out of IRACP.**
- The Outsourcing Directions, paragraph 100, repeal the earlier outsourcing
  guidance outright. Paragraph 17 carries the NBFC's responsibility for its
  service providers including recovery agents.

## Download these seven

Open each page and save the PDF into this folder under the filename given. The
PDF endpoints refuse automated fetches, so this step is manual.

| Save as | Master Direction | Page |
|---|---|---|
| `MD-NBFC-IRACP-2025.pdf` | NBFC – Income Recognition, Asset Classification and Provisioning Directions, 2025 (upd. 1 Jul 2026). RBI/DOR/2025-26/356, DOR.STR.REC.No.275/21.04.048/2025-26, 28 Nov 2025. **SMA buckets, DPD, NPA.** | https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12948 |
| `MD-NBFC-Outsourcing-2025.pdf` | NBFC – Managing Risks in Outsourcing Directions, 2025. RBI/DOR/2025-26/363, DOR.ORG.REC.No.282/21-04-158/2025-26, 28 Nov 2025. **Recovery agents (para 17), repeal (para 100).** | https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12941 |
| `MD-NBFC-ResponsibleBusinessConduct-2025.pdf` | NBFC – Responsible Business Conduct Directions, 2025 (upd. 1 Jul 2026). **Fair practices, contact conduct, penal charges.** | https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12942 |
| `MD-NBFC-StressedAssets-2025.pdf` | NBFC – Resolution of Stressed Assets Directions, 2025 (upd. 1 Jul 2026). **Upgradation, restructuring, settlement.** | https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12947 |
| `MD-NBFC-CreditInformationReporting-2025.pdf` | NBFC – Credit Information Reporting Directions, 2025 (upd. 1 Jul 2026). **Reporting cycle, customer alerts.** | https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12955 |
| `MD-NBFC-FraudRiskManagement-2026.pdf` | NBFC – Fraud Risk Management Directions, 2026, 31 Jul 2026. **EWS mandate, show cause notice.** | https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=13590 |
| `MD-NBFC-ScaleBasedRegulation-2025.pdf` | NBFC – Registration, Exemptions and Framework for Scale Based Regulation Directions, 2025 (upd. 1 Jul 2026). **Which layer we are, hence what applies.** | https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12965 |

Direct PDF link confirmed for IRACP:
https://rbidocs.rbi.org.in/rdocs/notification/PDFs/356MD4F8109CA54BE44A9805C5300601F8A11.PDF

## Once they are here

Every `source_ref` in `resources/policy/**/*.md` is stale and must be
re-derived against these documents — see `docs/26-open-items.md`. The old
circular references are kept in `docs/24-rbi-source-pack.md` as a record of what
the rules said before the restructure; they are not citations any more.
