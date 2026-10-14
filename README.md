# GmpTraqer

A local HTML dashboard for Indian IPOs, sourced from InvestorGain's current live GMP report and each IPO's detail page. Requires Python 3.9+; no packages or API keys.

## Run

```sh
python3 app.py
```

Open http://127.0.0.1:8765. Launching the server starts a fresh scrape; **Refresh data** updates it again. Requests are limited to one refresh per minute, with three concurrent detail fetches. Stop the server with Ctrl+C. Use `--port 8766` if needed.

Mainboard and unlisted IPOs are selected initially. Switch to SME or All IPOs, filter by status, search by company, sort numeric columns, or export the visible rows as CSV. Closed IPOs awaiting listing remain visible under “All unlisted”. “All statuses” includes the recently listed IPOs present in the source report; this is not a historical archive.

## Refresh without starting a server

```sh
python3 app.py --refresh
```

This writes `data/ipos.json` and a self-contained `dashboard.html`. Open `dashboard.html` directly for the saved table, including search, filters, sorting, and CSV export. A standalone HTML file cannot scrape the source directly; refresh it with the command above. The live dashboard reads background updates automatically. `python3 app.py --no-refresh` serves the saved data without scraping.

The daily 9:00 AM IST refresh is managed through the Codex automation associated with this chat. It executes the same `--refresh` command in this folder. Codex and the computer must be available for a local scheduled run. If a scheduled run is missed, launching the dashboard still refreshes the data.

## Data semantics

- Report: https://www.investorgain.com/report/ipo-gmp-live/331/
- Board, status, price, lot size, issue size, rating, and dates come from the report. The current report provides a bounded set of IPOs (50 when implemented); this tool does not claim to crawl all historical IPOs.
- GMP, GMP percentage, and estimated profit per lot come from the **first/latest row of each IPO's GMP history table**. The source's last-update text is displayed separately from the fetch time.
- Profit per lot is GMP × shares per lot, not necessarily the minimum application profit (particularly for SME applications).
- When a detail request fails, the report's GMP × lot size is shown with a **Calculated** label. Missing GMP remains missing, including when the report displays `--`; it is never silently treated as zero.
- An unknown/zero issue price suppresses the percentage and estimated listing price. Unknown lot size suppresses profit even if the source detail table uses a placeholder zero.
- The source's rating is shown as stars out of five. This is InvestorGain's rating, not a recommendation by this application.
- If the main report fails or becomes unparseable, the last successful snapshot remains intact. Per-detail failures are disclosed. Source markup changes may require updating the parser.
- All displayed times are IST. Source dates are preserved as published, without inventing a year.

## Verify

```sh
python3 -m unittest discover -s tests -v
```

Tests use saved table fixtures and synthetic edge cases; they do not contact the network. Live data and rendering should also be checked after changing the parser or frontend.
