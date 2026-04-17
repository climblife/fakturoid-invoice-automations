# ClimbLife Invoicing

Automatizace úkonů okolo fakturace firmy ClimbLife přes [Fakturoid API v3](https://www.fakturoid.cz/api/v3).

Aktuálně projekt umí zpracovat **Krabici na náklady** (Inbox Files): ze souborů v ní vytvoří regulérní, kompletně vyplněné a jako zaplacené označené náklady — extrakci dat z PDF/obrázku dělá Claude (obchází tak Fakturoid OCR).

## Nastavení

1. V repozitáři vytvoř `.env` s Fakturoid Client Credentials:
   ```
   FAKTUROID_CLIENT_ID=...
   FAKTUROID_CLIENT_SECRET=...
   ```
   (Volitelně `FAKTUROID_SLUG=climblife` — jinak se doplní z `/user.json`.)

2. Python venv + závislosti:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

## Použití

### Varianta A — celá Krabice přes Claude Code skill

V Claude Code v tomto adresáři řekni něco jako „zpracuj krabici" / „projdi inbox" — aktivuje se skill `process-fakturoid-inbox` (`.claude/skills/process-fakturoid-inbox/SKILL.md`), který v cyklu stahuje soubory, čte je, detekuje duplicity (Receipt + Invoice ke stejnému nákladu) a vytváří náklady. Skill se zastaví, když je Krabice prázdná.

### Varianta B — ruční běh

```bash
# Vylistuj vše v Krabici
.venv/bin/python inbox_to_expense.py list

# Stáhni konkrétní soubor (nebo první přes `fetch`)
.venv/bin/python inbox_to_expense.py download --id 835046
.venv/bin/python inbox_to_expense.py fetch

# Vyplň data.json podle schématu a vytvoř náklad
.venv/bin/python inbox_to_expense.py create --data data.json
```

`create` podporuje jeden soubor i pole `attachments: [{inbox_id, local_path}, ...]` pro dvojice Receipt + Invoice — první v pořadí je primární (preferuj Invoice). Po úspěšném vytvoření expense + platby skript smaže všechny uvedené soubory z Krabice. Při chybě soubory v Krabici zůstanou.

## Pravidla chování

Popsaná v `CLAUDE.md`. Stručně:

- **Dvojice Receipt + Invoice**: když v Krabici jsou oba soubory ke stejnému nákladu, vytvoří se **jeden náklad** s **oběma** soubory jako přílohy — Invoice první. Pokud už náklad se stejným dodavatelem + `original_number` v účtu existuje, nové soubory se z Krabice jen smažou.
- **Datum platby** = datum vystavení (faktury ClimbLife jdou automaticky kartou).
- **OCR**: dělá si ho Claude sám (multimodální čtení souboru). Fakturoid OCR přes API stejně dostupný není.
- V `private_note` každého vytvořeného nákladu je `"Vytvořeno pomocí Claude AI."` + odkaz na zdrojový `inbox_file_id`.

## Soubory

- `inbox_to_expense.py` — CLI skript s příkazy `fetch` a `create`
- `CLAUDE.md` — pravidla pro Claude (duplicity, platby, OCR)
- `.claude/skills/process-fakturoid-inbox/SKILL.md` — skill pro celou dávku
- `requirements.txt` — `requests`, `python-dotenv`
- `.env` — credentials (není v gitu)
- `tmp/` — dočasně stažené soubory (není v gitu)
- `data.json` — dočasný mezikrok mezi `fetch` a `create` (není v gitu)
