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

### Varianta B — ruční běh jednoho souboru

```bash
# 1. Stáhne první soubor z Krabice do tmp/ a vypíše JSON s metadaty
.venv/bin/python inbox_to_expense.py fetch

# 2. Podívej se na stažený PDF/obrázek a ručně vyplň data.json podle schématu
#    (viz .claude/skills/process-fakturoid-inbox/SKILL.md)

# 3. Vytvoří subject (pokud chybí), náklad s přílohou, platbu a smaže soubor z Krabice
.venv/bin/python inbox_to_expense.py create --data data.json
```

`inbox_to_expense.py create` dělá tyto kroky atomicky s safety netem — pokud se vytváření nákladu nepovede, soubor zůstane v Krabici.

## Pravidla chování

Popsaná v `CLAUDE.md`. Stručně:

- **Duplicity v Krabici** (Receipt + Invoice ke stejnému nákladu): před vytvořením nákladu zkontrolovat, jestli už existuje expense se stejným `supplier` + `original_number`. Pokud ano, duplicitní soubor jen smazat z Krabice, žádný nový náklad nevytvářet.
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
