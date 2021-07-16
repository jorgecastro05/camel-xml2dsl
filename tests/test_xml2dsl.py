import unittest
from xml2dsl.xml2dsl import xml_to_dsl
from unittest import TestCase, mock

class TestScript(unittest.TestCase):

    def test_upper(self):
        self.assertEqual(xml_to_dsl(), 0)

if __name__ == '__main__':
    unittest.main()