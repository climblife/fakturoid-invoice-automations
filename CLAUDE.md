# ClimbLife Invoicing — poznámky pro Claude

## Duplicity v Krabici na náklady

V Krabici (Fakturoid Inbox Files) se občas objeví **dva soubory k jednomu nákladu** — typicky **Receipt** (účtenka / platební potvrzení) a **Invoice** (faktura) od stejného dodavatele za stejné plnění.

**Pravidlo:** V takovém případě **nevytvářet duplicitní náklad**. Když se narazí na soubor, který se váže k již existujícímu nákladu, **jen smazat ten duplicitní záznam z Krabice** (bez vytvoření nového expense).

**Jak to poznat před vytvořením nákladu:** zkontrolovat, jestli už neexistuje expense se stejným `supplier` + `original_number`. Pokud číslo na dokladu chybí, porovnat podle kombinace dodavatel + částka + datum (± pár dní). Signály duplicity: stejný dodavatel, stejná částka, stejné/blízké datum, případně jiný typ přílohy (PDF vs obrázek, "receipt" vs "invoice" v názvu souboru).

**Akce při nalezení duplicity:** `DELETE /accounts/{slug}/inbox_files/{id}.json` a skončit. Žádné POST /expenses.

## Ostatní pravidla pro vytváření nákladů z Krabice

- Do `private_note` každého automaticky vytvořeného nákladu psát `"Vytvořeno pomocí Claude AI."` + odkaz na `inbox_file_id`.
- Faktury ClimbLife jsou typicky placené automaticky kartou → `paid_on` = `issued_on` (datum vystavení). Pokud by reálné datum platby bylo jiné, řeší se ex-post.
- OCR data si agent extrahuje sám čtením PDF/obrázku — Fakturoid OCR (`ocr_status`) se obchází, jeho výstup přes API stejně není dostupný.
