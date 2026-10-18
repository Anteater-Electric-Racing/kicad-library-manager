import csv
import io
from pathlib import Path
import tempfile
import unittest

from manager.storage import COLUMNS, Library, create_library


class CatalogCompatibilityTests(unittest.TestCase):
    def test_original_v2_catalog_reads_without_rewriting(self):
        with tempfile.TemporaryDirectory() as directory:
            library = create_library(Path(directory) / 'fixture', install_runtime=False)
            path = library.appdata / 'components.csv'
            columns = [c for c in COLUMNS if c not in ('Current_A', 'Voltage_V')]
            stream = io.StringIO()
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerow({**dict.fromkeys(columns, ''), 'ID': 'stable-id', 'MPN': 'fixture'})
            path.write_text(stream.getvalue())
            before = path.read_bytes()
            row = Library(library.root).rows()[0]
            self.assertEqual(row['ID'], 'stable-id')
            self.assertEqual(row['Current_A'], '')
            self.assertEqual(row['Voltage_V'], '')
            self.assertEqual(path.read_bytes(), before)
            path.write_bytes(before.replace(b'Manufacturer', b'UnknownColumn', 1))
            with self.assertRaisesRegex(ValueError, 'Unexpected catalog header'):
                library.rows()
