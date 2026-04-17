---
name: process-fakturoid-inbox
description: Zpracuje celou Krabici na náklady ve Fakturoidu (Inbox Files) pro projekt ClimbLife. Postupně pro každý soubor: stáhne ho, agent (Claude) z něj multimodálně přečte údaje, rozhodne, zda jde o duplicitu existujícího nákladu, a buď vytvoří nový zaplacený náklad, nebo jen smaže duplicitu z Krabice. Použij když uživatel požádá o zpracování Krabice, Inboxu, nákladů z Fakturoidu, nebo řekne věci jako "projdi krabici", "zpracuj inbox", "vytěž faktury", "udělej náklady z krabice".
---

# Zpracování celé Krabice na náklady ve Fakturoidu

Tento skill projde všechny soubory v Krabici (Fakturoid Inbox Files) a z každého udělá kompletní zaplacený náklad. Opakuje fetch → read → rozhodnutí → create/delete, dokud je Krabice prázdná.

## Předpoklady

- Pracuješ v adresáři `/Users/michal/projects/climblife/invoicing`.
- Existuje `.venv/` a `inbox_to_expense.py` s podporou subcommandů `fetch` a `create`.
- `.env` obsahuje `FAKTUROID_CLIENT_ID` a `FAKTUROID_CLIENT_SECRET`.
- Pravidla z `CLAUDE.md` v rootu projektu platí (duplicity, paid_on=issued_on, "Vytvořeno pomocí Claude AI" do private_note).

Pokud cokoli z toho chybí, zastav se a zeptej uživatele.

## Hlavní smyčka

Opakuj, dokud `fetch` nevrátí `{"empty": true}`:

### 1. Stáhni další soubor

```bash
.venv/bin/python inbox_to_expense.py fetch
```

Výstup je JSON. Pokud `empty: true` → Krabice je hotová, skonči a vypiš souhrn.

Jinak máš `inbox_id`, `filename`, `local_path`.

### 2. Přečti soubor

Použij `Read` s absolutní cestou (`/Users/michal/projects/climblife/invoicing/` + `local_path`). Multimodálně (PDF/JPG/PNG) z dokladu extrahuj:

- **supplier**: název, IČO (`registration_no`), DIČ (`vat_no`) — pokud jsou
- **original_number**: číslo dokladu od dodavatele
- **variable_symbol**: VS (často rovno `original_number` nebo z QR kódu)
- **issued_on**: datum vystavení (YYYY-MM-DD)
- **received_on**: obvykle = `issued_on`, pokud není jinde uvedeno
- **due_on**: datum splatnosti
- **taxable_fulfillment_due**: datum zdanitelného plnění (pokud faktura neobsahuje, použij `issued_on`)
- **currency**: CZK / EUR / USD / …
- **payment_method**: obvykle `card` (výchozí pro ClimbLife); `bank` u převodu
- **vat_price_mode**: `without_vat` u dokladu bez DPH nebo s reverse charge; `from_total_with_vat` u dokladu, kde máš jen celkové částky s DPH; `without_vat` když máš jasný rozpis base + VAT
- **lines**: co nejvěrněji z dokladu (name, quantity, unit_price, vat_rate); u jednoduchých dokladů stačí jeden řádek s celkovou sumou

### 3. Zkontroluj, jestli to není duplicita

**Toto je kritický krok.** V Krabici se občas objeví dva soubory k jednomu nákladu (typicky Receipt + Invoice od stejného dodavatele).

Zavolej pomocný skript (nebo inline Python přes `.venv/bin/python`) a najdi expenses s:

- stejným dodavatelem (subject match podle IČO nebo normalizovaného jména) **a**
- stejným `original_number` (primární kritérium)
- NEBO stejnou částkou + blízkým datem (± 5 dní), pokud `original_number` chybí

Endpoint: `GET /accounts/climblife/expenses.json?subject_id=...&number=...` (parametry: `subject_id`, `number`, `since`, `until`). Alternativně vylistovat posledních pár nákladů daného subjectu a porovnat lokálně.

**Pokud duplicita nalezena:**
- Vypiš `"Duplicita nalezena (expense_id=..., number=...), jen mažu z Krabice"`.
- Zavolej `DELETE /accounts/climblife/inbox_files/{inbox_id}.json` (např. inline přes curl / requests).
- Pokračuj další iterací (zpět na krok 1).
- **Nevolej `create`**.

### 4. Sestav `data.json` a vytvoř náklad

Pokud duplicita nenalezena, zapiš `data.json` s extrahovanými údaji (viz schéma níže) a zavolej:

```bash
.venv/bin/python inbox_to_expense.py create --data data.json
```

Skript udělá: find-or-create subject → create expense (s přílohou + `"Vytvořeno pomocí Claude AI."` v private_note) → payment (paid_on = issued_on, mark_document_as_paid) → DELETE inbox file.

Výstup obsahuje `expense_id`, `expense_html_url`, `subject_created`. Zaznamenej pro závěrečný souhrn.

### 5. Opakuj

Zpět na krok 1, dokud `fetch` nevrátí prázdnou Krabici.

## Schéma `data.json`

```json
{
  "inbox_id": 123,
  "local_path": "tmp/123__invoice.pdf",
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

## Bezpečnostní pravidla

- **Nikdy nemaž soubor z Krabice dříve, než je jisté, že buď (a) byl úspěšně vytvořen expense, nebo (b) jde prokazatelně o duplicitu.** Skript `create` to řeší, pro duplicity to musíš hlídat ručně (pořadí: ověř duplicitu → smaž).
- Pokud `create` selže (nenulový exit code), zastav smyčku a nahlaš uživateli — soubor je pořád v Krabici, dá se opravit a spustit znovu.
- Pokud nejsi schopen spolehlivě extrahovat klíčový údaj (dodavatel, datum, částka), zastav se a ukaž uživateli, co vidíš — ať rozhodne.
- Maximum iterací v jedné smyčce: 50 (ochrana před nekonečným během). Pokud je Krabice větší, uživatel to ví a spustí znovu.

## Závěrečný souhrn

Na konci vypiš stručnou tabulku: filename → akce (created expense X / duplicate of Y / error), a celkové počty. Pokud bylo něco vytvořeno, odkaž HTML URL.
