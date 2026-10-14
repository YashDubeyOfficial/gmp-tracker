from pathlib import Path
import unittest
from scraper import parse_report, parse_detail, enrich, scrape, number

FIXTURES = Path(__file__).parent / 'fixtures'


class ScraperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = (FIXTURES / 'report.html').read_text()

    def test_report_segments_and_status(self):
        rows = parse_report(self.report)
        self.assertEqual(len(rows), 50)
        by_id = {r['id']: r for r in rows}
        self.assertEqual(by_id['2306']['board'], 'Mainboard')
        self.assertEqual(by_id['2306']['status'], 'Upcoming')
        self.assertEqual(by_id['2006']['board'], 'SME')
        self.assertEqual(by_id['2235']['board'], 'Mainboard')
        self.assertEqual(by_id['2235']['lotSize'], 200)
        self.assertEqual(by_id['2235']['closeDate'], '5-Oct')
        self.assertTrue(any(r['status'] == 'Listed' for r in rows))
        self.assertFalse(any(r['status'] == 'Unknown' for r in rows))

    def test_detail_profit_is_per_lot(self):
        detail = parse_detail((FIXTURES / 'acme.html').read_text())
        self.assertEqual(detail['profitPerLot'], 39000)
        self.assertEqual(detail['gmpPercent'], 33.16)
        self.assertEqual(detail['gmp'], 65)
        self.assertEqual(detail['sourceUpdated'], '6-Oct 22:37')

    def test_unknown_price_and_lot_suppress_placeholder_zero(self):
        row = next(r for r in parse_report(self.report) if r['id'] == '2306')
        enrich(row, parse_detail((FIXTURES / 'jio.html').read_text()))
        self.assertEqual(row['gmp'], 167)
        self.assertIsNone(row['profitPerLot'])
        self.assertIsNone(row['gmpPercent'])
        self.assertIsNone(row['estimatedListing'])

    def test_nityas_latest_detail(self):
        detail = parse_detail((FIXTURES / 'nityas.html').read_text())
        self.assertEqual(detail['profitPerLot'], 200)
        self.assertEqual(detail['gmpPercent'], 1.33)
        self.assertEqual(detail['sourceUpdated'], '6-Oct 23:37')

    def test_zero_negative_and_missing_are_distinct(self):
        self.assertEqual(number('₹0'), 0)
        self.assertEqual(number('₹-1,234.50'), -1234.5)
        self.assertIsNone(number('₹--'))
        html = '<table><tr><td data-title="GMP">₹-5 (-2.00%)</td><td data-title="Est. Profit">₹-500</td></tr></table>'
        detail = parse_detail(html)
        self.assertEqual(detail['gmp'], -5)
        self.assertEqual(detail['profitPerLot'], -500)
        self.assertEqual(detail['gmpPercent'], -2)

    def test_missing_report_raises(self):
        with self.assertRaises(ValueError): parse_report('<html>Access denied</html>')
        with self.assertRaises(ValueError): parse_report('<table id="reportTable"></table>')

    def test_detail_failures_have_explicit_fallback(self):
        def fetch(url):
            if '/report/' in url: return self.report
            raise OSError('Unavailable')
        snapshot = scrape(fetch=fetch)
        self.assertEqual(len(snapshot['warnings']), 50)
        nityas = next(r for r in snapshot['rows'] if r['id'] == '2235')
        self.assertEqual(nityas['profitSource'], 'calculated')
        self.assertEqual(nityas['profitPerLot'], 200)
        self.assertTrue(any(r['gmp'] is None and r['profitPerLot'] is None for r in snapshot['rows']))


if __name__ == '__main__':
    unittest.main()
