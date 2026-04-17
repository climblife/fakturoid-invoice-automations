---
name: process-fakturoid-inbox
description: Zpracuje celou Krabici na náklady ve Fakturoidu (Inbox Files) pro projekt ClimbLife. Vylistuje všechny soubory, stáhne je, spáruje dvojice Receipt+Invoice a z každé dvojice (nebo samostatného souboru) vytvoří jeden kompletní zaplacený náklad se všemi přílohami. Použij když uživatel požádá o zpracování Krabice, Inboxu, nákladů z Fakturoidu, nebo řekne věci jako "projdi krabici", "zpracuj inbox", "vytěž faktury", "udělej náklady z krabice".
---

# Zpracování celé Krabice na náklady ve Fakturoidu

Tento skill projde všechny soubory v Krabici (Fakturoid Inbox Files), spáruje dvojice **Receipt + Invoice**, které se vážou ke stejnému nákladu, a z každé skupiny vytvoří jeden kompletní zaplacený náklad **se všemi přílohami**.

## Předpoklady

- Pracuješ v adresáři `/Users/michal/projects/climblife/invoicing`.
- Existuje `.venv/` a `inbox_to_expense.py` s podporou subcommandů `list`, `fetch`, `download`, `create`.
- `.env` obsahuje `FAKTUROID_CLIENT_ID` a `FAKTUROID_CLIENT_SECRET`.
- Pravidla z `CLAUDE.md` v rootu projektu platí.

Pokud cokoli z toho chybí, zastav se a zeptej uživatele.

## Workflow

### 1. Vylistuj Krabici

```bash
.venv/bin/python inbox_to_expense.py list
```

Výstup: `{slug, count, files: [{inbox_id, filename, bytes, ocr_status, created_at}, ...]}`.

Pokud `count == 0` → hotovo, vypiš souhrn a skonči.

### 2. Stáhni všechny soubory

Pro každý `inbox_id` z listu zavolej:

```bash
.venv/bin/python inbox_to_expense.py download --id <inbox_id>
```

Získáš `local_path` pro každý.

### 3. Přečti každý soubor

Pro každý stažený soubor použij `Read` s absolutní cestou. Multimodálně (PDF/JPG/PNG) z dokladu extrahuj:

- **supplier**: název, IČO (`registration_no`), DIČ (`vat_no`)
- **original_number**: číslo dokladu od dodavatele (**klíčové pro párování!**)
- **variable_symbol**: VS
- **issued_on / received_on / due_on / taxable_fulfillment_due** (YYYY-MM-DD)
- **currency** (CZK / EUR / USD / …)
- **payment_method**: obvykle `card`
- **vat_price_mode**: `without_vat` u reverse charge / bez DPH; `from_total_with_vat` když máš jen celkové částky s DPH
- **lines**: řádky dokladu
- **document_kind**: identifikuj, jestli jde o "invoice" / "receipt" / jiné (z názvu souboru, nadpisu PDF — typicky "Invoice" vs. "Receipt" / "Payment Receipt")
- **total**: celková částka (pro záložní párování, když chybí `original_number`)

### 4. Spáruj dvojice

Seskup soubory do skupin, kde sdílejí stejný "náklad". Kritéria:

- **Primární:** stejný normalizovaný `supplier.name` **a** stejný `original_number`.
- **Záložní** (když `original_number` chybí nebo se liší mezi Receipt a Invoice): stejný `supplier.name` + stejná `total` částka + stejné datum (± 2 dny).

Typický pattern u ClimbLife: Expo má páry `Receipt-XXXX.pdf` + `Invoice-XXXX.pdf` se stejným `original_number`. Anthropic podobně. DigitalOcean také má někdy zvlášť Invoice a Payment Receipt (receipt má vlastní ID, invoice má svoje — párují se podle stejného data + částky + dodavatele).

Výstupem této fáze je seznam **skupin**, každá obsahuje 1 nebo 2+ souborů.

### 5. Pro každou skupinu zkontroluj, že už expense neexistuje

Zavolej inline přes `.venv/bin/python`:

- `GET /accounts/climblife/expenses.json?subject_id=<id>` a prohlédni `original_number` / částku / datum nejbližších nákladů.
- Pokud se v účtu už **náklad** s těmito parametry vyskytuje, **nevytvářej duplikát**. Místo toho:
  - vypiš `"Náklad už existuje (expense_id=..., number=...), přílohy v Krabici mažu"`,
  - zavolej `DELETE /accounts/climblife/inbox_files/{id}.json` pro všechny soubory ve skupině,
  - pokračuj další skupinou.

### 6. Pro každou novou skupinu sestav `data.json` a zavolej `create`

**Preferuj Invoice nad Receipt** při extrakci hodnot: pokud skupina obsahuje oba typy, naplňuj `supplier`, `original_number`, `lines`, čísla apod. z **Invoice**. Receipt slouží primárně jako doklad o platbě.

Seřaď `attachments` tak, aby **Invoice byl první** (primární), Receipt druhý. Účetní pak v UI uvidí Invoice jako hlavní dokument.

Pokud skupina obsahuje jen jeden soubor, použij ho přímo.

Schéma `data.json` (rozšířené o `attachments[]`):

```json
{
  "attachments": [
    {"inbox_id": 123, "local_path": "tmp/123__Invoice-XXX.pdf"},
    {"inbox_id": 124, "local_path": "tmp/124__Receipt-XXX.pdf"}
  ],
  "supplier": {
    "name": "Dodavatel s.r.o.",
    "registration_no": "12345678",
    "vat_no": "CZ12345678"
  },
  "original_number": "2026-00123",
  "variable_symbol": "202600123",
  "issued_on": "2026-04-10",
  "received_on": "2026-04-10",
  "due_on": "2026-04-24",
  "taxable_fulfillment_due": "2026-04-10",
  "currency": "CZK",
  "payment_method": "card",
  "vat_price_mode": "from_total_with_vat",
  "description": "...",
  "lines": [
    {"name": "Popis", "quantity": "1", "unit_price": "1210", "vat_rate": "21"}
  ]
}
```

`paid_on` neuváděj — skript ho odvodí jako `issued_on`.

Zavolej:

```bash
.venv/bin/python inbox_to_expense.py create --data data.json
```

Skript vytvoří subject (pokud chybí), expense se všemi přílohami, platbu (`paid_on = issued_on`, `mark_document_as_paid`), a **smaže všechny připojené soubory z Krabice**.

### 7. Iteruj přes všechny skupiny a zapiš souhrn

## Bezpečnostní pravidla

- **Nikdy nemaž soubor z Krabice dříve, než je jisté, že byl buď (a) úspěšně připojen k novému nákladu, nebo (b) patří k již existujícímu nákladu.** Skript `create` to řeší — smaže jen po úspěšném vytvoření expense + platby.
- Pokud `create` selže (nenulový exit code), zastav skupinu a nahlaš uživateli. Soubory zůstanou v Krabici.
- Pokud nejsi schopen spolehlivě extrahovat klíčový údaj (dodavatel, datum, částka), nebo si nejsi jistý párováním, zastav se a ukaž uživateli, co vidíš — ať rozhodne.
- Pokud ve skupině něco nesedí (např. dvě "Invoice" se stejným číslem, nebo Receipt s jinou částkou než Invoice), radši se zastav a zeptej, než vytvářet chybný náklad.
- Maximum skupin v jedné dávce: 50.

## Závěrečný souhrn

Na konci vypiš stručnou tabulku: skupina → dodavatel → akce (created expense X s N přílohami / existing expense Y / error), a celkové počty. Pro vytvořené náklady odkaž HTML URL.
