# ClimbLife Invoicing — poznámky pro Claude

## Dvojice Receipt + Invoice v Krabici

V Krabici (Fakturoid Inbox Files) se často objeví **dva soubory k jednomu nákladu** — typicky **Receipt** (účtenka / platební potvrzení) a **Invoice** (faktura) od stejného dodavatele za stejné plnění.

**Pravidlo:** V takovém případě vytvořit **jeden náklad** a **připojit k němu oba soubory** jako přílohy. Preferovat **Invoice** — data z něj mají přednost při vyplňování nákladu a v seřazení příloh je Invoice první (účetní ho má radši jako primární dokument).

**Jak je spárovat:** soubory patří k sobě, když mají stejného `supplier` a stejný `original_number`. Pokud čísla chybí nebo se liší (DigitalOcean: Invoice a Payment Receipt mají každý vlastní ID), porovnat podle kombinace dodavatel + částka + datum (± pár dní). Signály páru: stejný dodavatel, stejná částka, stejné/blízké datum, dvojice "Receipt-XXX" + "Invoice-XXX" v názvech souborů.

**Když už náklad existuje** (např. byl vytvořen dřív a Krabice dostala jen další doklad k němu): **nevytvářet nový expense**, jen **smazat soubory z Krabice** — `DELETE /accounts/{slug}/inbox_files/{id}.json`. Žádné další POST /expenses.

**Skript `inbox_to_expense.py create`** umí pole `attachments: [{inbox_id, local_path}, ...]` — první v pořadí bude přiložený jako primární. Po úspěšném vytvoření nákladu smaže všechny uvedené soubory z Krabice.

## Ostatní pravidla pro vytváření nákladů z Krabice

- Do `private_note` každého automaticky vytvořeného nákladu psát `"Vytvořeno pomocí Claude AI."` + odkaz na `inbox_file_id`.
- Faktury ClimbLife jsou typicky placené automaticky kartou → `paid_on` = `issued_on` (datum vystavení). Pokud by reálné datum platby bylo jiné, řeší se ex-post.
- OCR data si agent extrahuje sám čtením PDF/obrázku — Fakturoid OCR (`ocr_status`) se obchází, jeho výstup přes API stejně není dostupný.
